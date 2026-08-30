"""
Tool functions + schemas for the triage agent.

STATUS: not started. Comes after trace.py is filled in — these functions will
need to write step records into a CaseTrace, so that interface needs to exist
first (or at least be stable) before this file is worth designing against.

Reference: DESIGN.md §6.
"""
from typing import Any, Literal

import sys
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env file, sets values as environment variables

DOCUMENT_QA_APP_SRC = os.environ.get("DOCUMENT_QA_APP_SRC")
if DOCUMENT_QA_APP_SRC is None:
    raise ValueError(f"Document QA application path not found")

if DOCUMENT_QA_APP_SRC:
    sys.path.append(DOCUMENT_QA_APP_SRC)

from src.retrieval import query_chunks
from src.generation import generate_answer

def classify_case(category: str, urgency: str) -> dict[str, Any]:
    """
    Receives the category/urgency the model has already determined by reasoning
    over the ticket text. 
    """
    VALID_CATEGORIES = {"billing", "legal", "refund", "technical", "account", "general"}
    VALID_URGENCIES = {"low", "medium", "high", "critical"}
    
    if category not in VALID_CATEGORIES:
        raise ValueError(f"invalid category: '{category}'")
    if urgency not in VALID_URGENCIES:
        raise ValueError(f"invalid urgency: '{urgency}'")     
    return {
            "category":category,
            "urgency":urgency
        }
            
classify_case_schema = {
    "name": "classify_case",
    "description": "Classify the incoming support case by category and urgency, based on the case text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["billing", "legal", "refund", "technical", "account", "general"],
                "description": "The category that best matches the case."
            },
            "urgency": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "How urgent the case appears to be."
            }
        },
        "required": ["category", "urgency"]
    }
}

def route_to_queue(queue: str, reason: str) -> dict[str, Any]:
    """
    Routes the ticket to the suggested queue. 
    """
    VALID_QUEUE = {"billing", "technical", "account", "general"}
    
    if queue not in VALID_QUEUE:
        raise ValueError(f"invalid queue: '{queue}'")
    if not reason.strip():
            raise ValueError(f"No reason: '{reason}'")     
    return {
            "queue":queue,
            "reason":reason
        }
    
route_to_queue_schema = {
    "name": "route_to_queue",
    "description": "Route the case to the queue the model has already selected, with a reason explaining the choice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "queue": {
                "type": "string",
                "enum": ["billing", "technical", "account", "general"],
                "description": "The queue that best matches the case."
            },
            "reason": {
                "type": "string",
                "description": "Reason for routing to the queue. It cannot be empty"
            }
        },
        "required": ["queue", "reason"]
    }
}


def escalate(reason: str) -> dict[str, Any]:
    """
    escalates the ticket. 
    """
    if not reason.strip():
            raise ValueError(f"No reason: '{reason}'")     
    return {
            "reason":reason
        }

escalate_schema = {
    "name": "escalate",
    "description": "escalate the case with a reason explaining the choice.",
    "input_schema": {
        "type": "object",
        "properties": {
             "reason": {
                "type": "string",
                "description": "Reason for case escalation. It cannot be empty"
            }
        },
        "required": ["reason"]
    }
}

KNOWLEDGE_BASE_COLLECTION = "support_kb"  # the one fixed collection name, decided earlier

def search_knowledge_base(query: str, model, chroma_client, anthropic_client) -> dict[str, Any]:
    """
    Query the shared support knowledge base and generate an answer.

    'query' is the only parameter the MODEL decides — it's what appears in
    the tool schema. 'model', 'chroma_client', 'anthropic_client' are
    infrastructure your own code supplies; they never appear in the tool
    schema, since the LLM has no concept of them.

    Reuses query_chunks() and generate_answer() from the Document Q&A
    pipeline directly — does NOT call answer_question(), since that
    function's ingestion logic doesn't apply here (the KB is a static,
    pre-ingested collection, not a per-request upload).
    """
    matched_chunks = query_chunks(query,model,chroma_client,KNOWLEDGE_BASE_COLLECTION, n_results=5 )
    top_similarity = 1 - matched_chunks[0]["distance"]
    chunks_used = [chunk["chunk_text"] for chunk in matched_chunks]
    answer = generate_answer(query, matched_chunks, anthropic_client)
    return {
        "answer": answer, 
        "top_similarity": top_similarity, 
        "chunks_used": chunks_used       
    }
    
search_knowledge_base_schema = {
    "name": "search_knowledge_base",
    "description": "Search the knowledge base for information relevant to the case and generate a candidate answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The question that needs to be answered."
            },
           },
        "required": ["query"]
    }
}

def check_layer_1_hard_rules(category: str, urgency: str) -> dict[str, Any]:
    """
    Layer 1: hard category/urgency rules. Non-negotiable — checked before
    any retrieval-based or self-reported confidence signal is consulted.
    """
    if not category.strip() or not urgency.strip :
        raise ValueError(f"category or urgency is blank")
    if category in {"billing", "legal", "refund"} and urgency == "critical":
        reason = f"blocked: category is {category} and urgency is {urgency}"
        resolve = "blocked"
    elif category in {"billing", "legal", "refund"}: 
        reason = f"blocked: category is {category}"
        resolve = "blocked"
    elif urgency == "critical": 
        reason = f"blocked: urgency is {urgency}"
        resolve = "blocked"
    else:
        reason = "category and urgency did not trigger a Layer 1 block"
        resolve = "continue"
        
    return {
        "resolve": resolve,
        "reason" : reason
            }
       
    
        