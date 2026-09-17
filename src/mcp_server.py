# src/mcp_server.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic
import chromadb
from typing import Any , Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from uuid import uuid4


from tools import classify_case , route_to_queue , escalate , search_knowledge_base , propose_resolution
from src.retrieval import load_model

mcp = MCPServer("SupportTriage")

case_state: dict[str, dict[str, Any]] = {}
anthropic_client = anthropic.Anthropic()
chroma_client = chromadb.PersistentClient(path="data/chroma_db")
model = load_model()


@mcp.tool(name="classify_case")
def classify_case_tool(category: Literal["billing", "legal", "refund", "technical", "account", "general"], 
                       urgency:  Literal["low", "medium", "high", "critical"]) -> dict[str, Any]:
    try:
        result = classify_case(category, urgency)
    except ValueError as e:
        raise ToolError(f"invalid classify_case input: {e}")
    case_handle = str(uuid4())
    case_state[case_handle] = result
    return {**result, "case_handle": case_handle}
    
    
@mcp.tool(name="route_to_queue")
def route_to_queue_tool(queue: Literal["billing", "technical", "account", "general"], reason: str , case_handle: str) -> dict[str, Any]:
    try:
        result = route_to_queue(queue, reason)
    except ValueError as e:
        raise ToolError(f"invalid classify_case input: {e}")
    case_state.pop(case_handle, None) 
    return result 

@mcp.tool(name="escalate")
def escalate_tool(reason: str ,case_handle: str) -> dict[str, Any]:
    try:
        result =  escalate(reason)
    except ValueError as e:
        raise ToolError(f"invalid classify_case input: {e}")
    case_state.pop(case_handle, None) 
    return result

@mcp.tool(name="search_knowledge_base")
def search_knowledge_base_tool(query: str, case_handle: str) -> dict[str, Any]:
    if case_handle not in case_state:
        raise ToolError(f"invalid case handle: '{case_handle}'")
    try:
        result =  search_knowledge_base(query, model, chroma_client, anthropic_client)
    except ValueError as e:
        raise ToolError(f"invalid search_knowledge_base input: {e}")
    case_state[case_handle]["top_similarity"] = result["top_similarity"]
    return {**result, "case_handle": case_handle}
    
@mcp.tool(name="propose_resolution")
def propose_resolution_tool(proposed_answer: str, self_reported_confidence: Literal["low", "medium", "high"], case_handle: str) -> dict[str, Any]:
    if case_handle not in case_state:
        raise ToolError(f"invalid case handle: '{case_handle}'")
    state = case_state[case_handle]
    if "top_similarity" not in state:
        raise ToolError("search_knowledge_base_tool must be called for this case before propose_resolution_tool")
    try:
        result = propose_resolution(proposed_answer, self_reported_confidence, state["category"], state["urgency"], state["top_similarity"])
    except ValueError as e:
        raise ToolError(f"invalid propose_resolution input: {e}")
    if result["status"] == "passed":
        case_state.pop(case_handle, None)
    return result
    
if __name__ == "__main__":
    mcp.run()