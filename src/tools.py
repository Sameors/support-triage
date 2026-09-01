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

VALID_CATEGORIES = {"billing", "legal", "refund", "technical", "account", "general"}
VALID_URGENCIES = {"low", "medium", "high", "critical"}
VALID_QUEUE = {"billing", "technical", "account", "general"}
VALID_CONFIDENCE_LEVELS = {"low", "medium", "high"}
SIMILARITY_THRESHOLD = 0.5

def classify_case(category: str, urgency: str) -> dict[str, Any]:
    """
    Receives the category/urgency the model has already determined by reasoning
    over the ticket text. 
    """
   
    
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
    
def check_layer_2_retrieval_confidence(top_similarity: float, threshold: float) -> dict[str, Any]:
    """
    Layer 2: confidence /treshold rules. Non-negotiable — evalautes the 
    retrievel confidence from knowledge base.
    """
    if top_similarity is None or threshold is None:
        raise ValueError(f"similarity or threshold is blank")
    if top_similarity < threshold:
        reason = f"blocked: confidence is {top_similarity} and threshold is {threshold}"
        resolve = "blocked"
    else:
        reason = f"confidence: {top_similarity} and treshold : {threshold} did not trigger a Layer 2 block"
        resolve = "continue"
        
    return {
        "resolve": resolve,
        "reason" : reason
            }
       
def check_layer_3_self_reported_tiebreaker(self_reported_confidence: str) -> dict[str, Any]:
    """
    Layer 3: model reported confidence rules. Non-negotiable — evalautes the 
    retrievel confidence from the model.
    """
    

    if self_reported_confidence not in VALID_CONFIDENCE_LEVELS:
        raise ValueError(f"invalid self_reported_confidence: '{self_reported_confidence}'")
    if self_reported_confidence == "low":
        reason = f"blocked: model confidence is {self_reported_confidence}"
        resolve = "blocked"
    else:
        reason = f"model confidence: {self_reported_confidence}"
        resolve = "continue"
                
    return {
            "resolve": resolve,
            "reason" : reason
            }

def propose_resolution(
    proposed_answer: str, self_reported_confidence: str,category: str,
    urgency: str,top_similarity: float) -> dict[str, Any]:
    
    layer1_check = check_layer_1_hard_rules(category,urgency)
    if layer1_check["resolve"] == "blocked":
        return {"status":"blocked" , "proposed_answer":proposed_answer , "layer_1":layer1_check , "layer_2":"None" , "layer_3":"None"}
    layer2_check = check_layer_2_retrieval_confidence(top_similarity,SIMILARITY_THRESHOLD)
    if layer2_check["resolve"] == "blocked":
        return {"status":"blocked" , "proposed_answer":proposed_answer, "layer_1":layer1_check , "layer_2":layer2_check , "layer_3":"None"}
    layer3_check = check_layer_3_self_reported_tiebreaker(self_reported_confidence)
    if layer3_check["resolve"] == "blocked":
        return {"status":"blocked" , "proposed_answer":proposed_answer ,"layer_1":layer1_check , "layer_2":layer2_check , "layer_3":layer3_check}
    return {"status":"passed" , "proposed_answer":proposed_answer, "layer_1":layer1_check , "layer_2":layer2_check , "layer_3":layer3_check}

propose_resolution_schema = {
    "name": "propose_resolution",
    "description": '''Propose a resolution to the case, with your confidence in it. This does not resolve the case directly 
                    — it triggers a verification check that may block the resolution.''',
    "input_schema": {
        "type": "object",
        "properties": {
            "proposed_answer": {
                "type": "string",
                "description": "The draft answer you propose sending to resolve the case."
            },
            "self_reported_confidence": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "How confident you are in this proposed answer."
                        },
           },
        "required": ["proposed_answer","self_reported_confidence"]
    }
}