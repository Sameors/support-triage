"""
The agent reasoning loop.
 
Design reference: DESIGN.md §4 (Architecture: tool-calling reasoning loop).
 
This is the orchestrator: it ties together trace.py (CaseTrace, make_step_record)
and tools.py (the five tool functions + schemas) with a real, hand-written loop
against the Anthropic API.
 
Reasoning already established (don't re-derive, just implement):
  - Tool dispatch: a dict mapping tool name strings -> actual function objects,
    looked up and called via **kwargs unpacking. NOT an if/elif chain.
  - Two categories of "extra" arguments beyond what the model provides in
    tool_input:
      * INFRASTRUCTURE (model, chroma_client, anthropic_client) — created ONCE,
        before the loop starts, never changes during a case's run.
      * TRACKED_STATE (category, urgency, top_similarity) — starts empty,
        gets populated SELECTIVELY (only the specific fields a later tool
        needs) as earlier tool results come back during the loop.
  - trace.add_step() is called from HERE, uniformly, for every tool_call and
    every rule_check — NOT from inside individual tool functions.
"""
import anthropic
import chromadb
from typing import Any
from src.trace import CaseTrace, make_step_record
from src.tools import (
    classify_case, route_to_queue, escalate, search_knowledge_base, propose_resolution,
    classify_case_schema, route_to_queue_schema, escalate_schema,
    search_knowledge_base_schema, propose_resolution_schema
)
from src.embedding import load_model
# ---------------------------------------------------------------------------
# exception handlers.
# ---------------------------------------------------------------------------
class ToolSequenceError(Exception):
    """Raised when a tool is called before its required prerequisite state exists in tracked_state."""
    pass

class UnknownToolError(Exception):
    """Raised when a unknown tool is is returned by model."""
    pass
# ---------------------------------------------------------------------------
# Tool dispatch table — maps tool name (string) -> actual function object.
# ---------------------------------------------------------------------------

infrastructure = {
    "anthropic_client": anthropic.Anthropic(),
    "claude_model_name": "claude-haiku-4-5-20251001",
    "chroma_client": chromadb.PersistentClient(path="data/chroma_db"),
    "model": load_model(),
}
 
TOOL_FUNCTIONS = {
    "classify_case": classify_case,
    "route_to_queue": route_to_queue,
    "escalate": escalate,
    "search_knowledge_base": search_knowledge_base,
    "propose_resolution": propose_resolution,
}
 
ALL_TOOL_SCHEMAS = [classify_case_schema, route_to_queue_schema, escalate_schema,
    search_knowledge_base_schema, propose_resolution_schema]
 
 
# ---------------------------------------------------------------------------
# Guard rails — NOT yet discussed in detail. Design these before implementing.
# ---------------------------------------------------------------------------
 
MAX_ITERATIONS = 5  # placeholder, per DESIGN.md §4 — tune later


# ---------------------------------------------------------------------------
# Guard the duplicate tool calls in single iteration or cross iteration model calls.
# ---------------------------------------------------------------------------
def check_repeat_call_guard(tool_call_history: list[dict], tool_name: str, tool_input: dict) -> dict | None:
    """
    Checks tool_call_history for a prior entry with the same tool_name + tool_input.
    Returns the matching history entry (dict with at least 'result') if found, else None.
    Read-only — does not mutate tool_call_history. Caller owns appending.
    """
    for entry in tool_call_history:
        if entry["tool_name"] == tool_name and entry["tool_input"] == tool_input:
            return entry
    return None
   
# ---------------------------------------------------------------------------
# The system prompt — establishes the mandatory classify_case-first rule,
# per DESIGN.md §3 and the "resent every single turn" mechanic you already
# worked through conceptually. Not yet written as an actual string.
# ---------------------------------------------------------------------------
 
def build_system_prompt() -> str:
    """
    role/purpose of the agent, and the classify_case-first rule and evaluate the final decision. 
    """
    return """You are a support case triage agent who takes the user input , 
                Always call classify_case as a first tool to determine the category and urgency of the support case. 
                Based on the models response suggestion evaluate next best matched tool from those available 
                and continue evaluating untill a final decision [resolving, routing, or escalating] is obtained . 
                Always attempt propose_resolution for every case before calling 
                route_to_queue or escalate, unless the retrieved knowledge base content explicitly states the 
                issue cannot be resolved through this system.

                Do not route or escalate directly based on your own judgment that a case 
                "requires specialized support" or "needs human verification" — let 
                propose_resolution's confidence layers make that determination instead.
                Once propose_resolution returns a blocked status, choose between 
                route_to_queue and escalate based on the nature of the case:

                Call escalate if the ticket describes more than one distinct issue, or 
                does not fit cleanly into a single category — re-read the original 
                ticket text to check for this, not just the classified category.

                Call route_to_queue if the ticket is a single, clearly categorized 
                issue that a human simply needs to execute or verify, even if it 
                couldn't be auto-resolved."""
# ---------------------------------------------------------------------------
# Tool execution — the dict lookup + selective tracked_state merging you
# already reasoned through. Implement it here.
# ---------------------------------------------------------------------------
 
def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    tracked_state: dict[str, Any],
    infrastructure: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any]:
    """
    Looks up the right function via TOOL_FUNCTIONS, merges tool_input with
    whatever extra args that specific tool needs (infrastructure for
    search_knowledge_base; tracked_state for propose_resolution; neither for
    the other three), and actually calls it.
     """
    if tool_name not in TOOL_FUNCTIONS:
        raise UnknownToolError(f"tool_name cannot be found. tool_name: {tool_name}")

    func = TOOL_FUNCTIONS[tool_name]
    extra_args = TOOL_EXTRA_ARGS_BUILDERS[tool_name](tracked_state, infrastructure ,case)
    result = func(**tool_input, **extra_args)
    update_tracked_state(tracked_state, tool_name, result)
    return result
  
# ---------------------------------------------------------------------------
# Updating tracked_state after a tool call returns — the SELECTIVE extraction
# you already reasoned through (pull out only what's needed, not the whole
# result dict).
# ---------------------------------------------------------------------------
 
def update_tracked_state(tracked_state: dict[str, Any], tool_name: str, tool_result: dict[str, Any]) -> None:
    """
    After classify_case returns, tracked_state needs "category" and "urgency"
    pulled out of the result. After search_knowledge_base returns,
    tracked_state needs "top_similarity" pulled out 
    """
    if tool_name == "classify_case":
        tracked_state["category"] = tool_result["category"] 
        tracked_state["urgency"] = tool_result["urgency"] 
    elif tool_name == "search_knowledge_base":
        tracked_state["top_similarity"] = tool_result["top_similarity"] 
    # all other tools: nothing to track
 
# ---------------------------------------------------------------------------
# stand alone functions for extra_args
# ---------------------------------------------------------------------------

def _no_extra_args(tracked_state, infrastructure,case):
    return {}

def _search_kb_extra_args(tracked_state, infrastructure, case):
    return {
        "model": infrastructure["model"],
        "chroma_client": infrastructure["chroma_client"],
        "anthropic_client": infrastructure["anthropic_client"],
        "query" : case["text"]
    }

def _propose_resolution_extra_args(tracked_state, infrastructure,case):
    required_keys = {"category", "urgency", "top_similarity"}
    missing = required_keys - tracked_state.keys()
    if missing:
        raise ToolSequenceError(f"propose_resolution called before required state was available. Missing: {missing}")
    return {k: tracked_state[k] for k in required_keys}

TOOL_EXTRA_ARGS_BUILDERS = {
    "classify_case": _no_extra_args,
    "route_to_queue": _no_extra_args,
    "escalate": _no_extra_args,
    "search_knowledge_base": _search_kb_extra_args,
    "propose_resolution": _propose_resolution_extra_args,
}

FINAL_ACTION_MAP = {
    "propose_resolution": "resolve",
    "route_to_queue": "route",
    "escalate": "escalate",
}
# ---------------------------------------------------------------------------
# check if its final step.
# ---------------------------------------------------------------------------
def is_final_step(tool_name: str, tool_result: dict) -> bool:
    if tool_name in {"route_to_queue", "escalate"}:
        return True
    if tool_name == "propose_resolution":
        return tool_result.get("status") == "passed"
    return False
 
# ---------------------------------------------------------------------------
# The main loop itself.
# ---------------------------------------------------------------------------
 
def run_agent_on_case(case: dict[str, Any], infrastructure: dict[str, Any]) -> dict[str, Any]:
    """
    Runs the full reasoning loop for one case, start to finish.
 
    case: {"id": ..., "text": ..., "customer_tier": ..., "previous_ticket_count": ...}
          per DATASET.md's ticket schema.
    infrastructure: {"model": ..., "chroma_client": ..., "anthropic_client": ...}
          created ONCE, outside this function, passed in.
      """
    trace = CaseTrace(case_id=case["id"])
    tracked_state = {}
    tool_call_history = []
    messages=[{"role": "user", "content":case["text"]}]
    system_prompt_string=build_system_prompt()
    iteration = 0
    while True:
        iteration += 1
        if iteration > MAX_ITERATIONS:
            print(f"Exceeded max iterations ({MAX_ITERATIONS}), forcing escalate")
            trace.add_step(make_step_record(step_number=iteration, step_type="timeout_escalate", 
                                            name="iteration_cap", details={"reason": "max iterations passed"}))
            trace.set_final_action("timeout_escalate")
            final_result = {"case_id": case["id"], "final_action":"timeout_escalate","trace": trace.to_dict() }
            return final_result
        response = infrastructure["anthropic_client"].messages.create(
                                model=infrastructure["claude_model_name"],
                                max_tokens=1024,
                                system=system_prompt_string,
                                tools=ALL_TOOL_SCHEMAS,
                                messages=messages
                                )
        messages.append({"role": "assistant", "content": response.content})
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        #print(f"iteration {iteration}: response.content = {response.content}")
        print(f"iteration {iteration}: stop_reason={response.stop_reason}, tools_called={[b.name for b in tool_use_blocks]}")
        classify_case_done = "category" in tracked_state

        if not tool_use_blocks:
            if not classify_case_done:
                messages.append({"role": "user", "content": "You must call classify_case first."})
            else:
                messages.append({"role": "user", "content": "You must call a tool to proceed."})
            continue

        else:
            case_terminated = False
            final_result = None
            tool_results_this_turn = []
            for i, tool_block in enumerate(tool_use_blocks):
                classify_case_done = "category" in tracked_state
                if not classify_case_done and tool_block.name != "classify_case":
                    messages.append({"role": "user", "content": "You must call classify_case before any other tool."})
                    trace.add_step(make_step_record(step_number=iteration, step_type="correction", name=tool_block.name, details={"reason": "wrong_tool", "expected": "classify_case"}))
                    continue
                duplicate = check_repeat_call_guard(tool_call_history, tool_block.name, tool_block.input)
                if duplicate is not None:
                    duplicate_msg = (
                                    f"Duplicate call detected: {tool_block.name} already called with identical "
                                    f"inputs. Prior result: {duplicate['result']}. "
                                    f"Do not retry this tool. Call `escalate` now."
                                    )
                    tool_results_this_turn.append({"type": "tool_result", "tool_use_id": tool_block.id, "content": duplicate_msg})
                    break
                try:
                    tool_output = execute_tool(tool_block.name, tool_block.input, tracked_state, infrastructure,case)
                    trace.add_step(make_step_record(step_number=iteration, step_type="tool_call", name=tool_block.name, details=tool_output))
                    tool_call_history.append({"tool_name": tool_block.name, "tool_input": tool_block.input, "result": tool_output})
                    tool_results_this_turn.append({"type": "tool_result", "tool_use_id": tool_block.id, 
                                                   "content": str(tool_output)})
                    

                    if is_final_step(tool_block.name, tool_output):
                                        trace.set_final_action(FINAL_ACTION_MAP[tool_block.name])
                                        final_result = {
                                            "case_id": case["id"],
                                            "final_action": FINAL_ACTION_MAP[tool_block.name],
                                            "trace": trace.to_dict(),
                                            }
                                        case_terminated = True
                                        break
            
                except (UnknownToolError, ToolSequenceError) as e:
                    print(f"Iteration {iteration}: fatal tool error — {type(e).__name__}: {e}")
                    final_result = {
                    "case_id": case["id"],
                    "final_action": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "trace": trace.to_dict() }
                    tool_results_this_turn.append({"type": "tool_result", "tool_use_id": tool_block.id, "content": 
                                                    f"Error: {e}"})
                    trace.add_step(make_step_record(step_number=iteration, step_type="error", name=tool_block.name, 
                                                    details={"error_type": type(e).__name__, "error_message": str(e), 
                                                             "tracked_state": tracked_state}))

                    case_terminated = True
                    break
            
                except KeyError as e:
                    final_result = {
                                    "case_id": case["id"],
                                    "final_action": "error",
                                    "error_type": "MissingInfrastructureKey",
                                    "error_message": str(e),
                                    "trace": trace.to_dict() }
                    tool_results_this_turn.append({"type": "tool_result", "tool_use_id": tool_block.id, "content": 
                                                                        f"Error: {e}"})
                    trace.add_step(make_step_record(step_number=iteration, step_type="error", name=tool_block.name, 
                                                                        details={"error_type": type(e).__name__, "error_message": str(e), 
                                                                                 "tracked_state": tracked_state}))
                    
                    case_terminated = True
                    break
            skip_reason = "case already concluded" if case_terminated else "duplicate call detected this turn — awaiting escalation"
            for skipped_block in tool_use_blocks[i+1:]:
                tool_results_this_turn.append({"type": "tool_result", "tool_use_id": skipped_block.id, "content": f"Not executed — {skip_reason}."})
            messages.append({"role": "user", "content": tool_results_this_turn})
            
            if case_terminated:
                return final_result

        
            
        