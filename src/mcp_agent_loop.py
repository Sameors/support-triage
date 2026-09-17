import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json

import asyncio  
from typing import Any
from mcp import Client, StdioServerParameters
from src.trace import CaseTrace, make_step_record
from src.agent_loop import MAX_ITERATIONS
from src.agent_loop import build_system_prompt as build_base_system_prompt , check_repeat_call_guard , is_final_step ,FINAL_ACTION_MAP

def build_system_prompt_mcp() -> str:
    return build_base_system_prompt() + """
        After classify_case returns a case_handle, include that exact case_handle value
        as an argument in every subsequent tool call for this same case."""

# async def run_agent_on_case_mcp(case: dict[str, Any], anthropic_client, claude_model_name: str) -> dict[str, Any]:
#     server_params = StdioServerParameters(
#         command="python",
#         args=["src/mcp_server.py"],
#     )
async def run_agent_on_case_mcp(case: dict[str, Any], client, anthropic_client, claude_model_name: str) -> dict[str, Any]:
    tools_result = await client.list_tools()
    tool_schemas = [
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
        for tool in tools_result.tools]
    trace = CaseTrace(case_id=case["id"])
    case_handle = None
    tool_call_history = []
    messages = [{"role": "user", "content": case["text"]}]
    system_prompt_string = build_system_prompt_mcp()
    iteration = 0
    while True:
        iteration += 1
        if iteration > MAX_ITERATIONS:
            print(f"Exceeded max iterations ({MAX_ITERATIONS}), forcing escalate")
            trace.add_step(make_step_record(step_number=iteration, step_type="timeout_escalate",
                                            name="iteration_cap", details={"reason": "max iterations passed"}))
            trace.set_final_action("timeout_escalate")
            return {"case_id": case["id"], "final_action": "timeout_escalate", "trace": trace.to_dict()}

        response = anthropic_client.messages.create(
            model=claude_model_name,
            max_tokens=1024,
            system=system_prompt_string,
            tools=tool_schemas,
            messages=messages
        )
        messages.append({"role": "assistant", "content": response.content})
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        classify_case_done = case_handle is not None

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
                classify_case_done = case_handle is not None
                if not classify_case_done and tool_block.name != "classify_case":
                    messages.append({"role": "user", "content": "You must call classify_case before any other tool."})
                    trace.add_step(make_step_record(step_number=iteration, step_type="correction", name=tool_block.name, details={"reason": "wrong_tool", "expected": "classify_case"}))
                    continue

                duplicate = check_repeat_call_guard(tool_call_history, tool_block.name, tool_block.input)
                if duplicate is not None:
                    duplicate_msg = (
                        f"Duplicate call detected: {tool_block.name} already called with identical "
                        f"inputs. Prior result: {duplicate['result']}."
                        f"Do not retry this tool. Call `escalate` now."
                    )
                    trace.add_step(make_step_record(step_number=iteration, step_type="duplicate_call", name=tool_block.name, details=duplicate_msg))
                    tool_results_this_turn.append({"type": "tool_result", "tool_use_id": tool_block.id, "content": duplicate_msg})
                    break
                try:
                    tool_result = await client.call_tool(tool_block.name, tool_block.input)
                except Exception as e:
                    print(f"Iteration {iteration}: fatal transport error — {type(e).__name__}: {e}")
                    trace.add_step(make_step_record(step_number=iteration, step_type="error", name=tool_block.name, details={"error_type": type(e).__name__, "error_message": str(e)}))
                    final_result = {"case_id": case["id"], "final_action": "error", "error_type": type(e).__name__, "error_message": str(e), "trace": trace.to_dict()}
                    case_terminated = True
                    break
                if tool_result.is_error:
                    error_text = tool_result.content[0].text
                    trace.add_step(make_step_record(step_number=iteration, step_type="tool_error", name=tool_block.name, details={"error": error_text}))
                    tool_results_this_turn.append({"type": "tool_result", "tool_use_id": tool_block.id, "content": error_text})
                else:
                    result_data = tool_result.structured_content
                    if tool_block.name == "classify_case":
                        case_handle = tool_result.structured_content["case_handle"]  # pull it out of result_data — what key?
                    trace.add_step(make_step_record(step_number=iteration, step_type="tool_call", name=tool_block.name, details=result_data))
                    tool_call_history.append({"tool_name": tool_block.name, "tool_input": tool_block.input, "result": result_data})
                    tool_results_this_turn.append({"type": "tool_result", "tool_use_id": tool_block.id, "content": str(result_data)})

                    if is_final_step(tool_block.name, result_data):
                        trace.set_final_action(FINAL_ACTION_MAP[tool_block.name])
                        final_result = {"case_id": case["id"], "final_action": FINAL_ACTION_MAP[tool_block.name], "trace": trace.to_dict()}
                        case_terminated = True
                        break
            skip_reason = "case already concluded" if case_terminated else "duplicate call detected this turn — awaiting escalation"
            for skipped_block in tool_use_blocks[i+1:]:
                tool_results_this_turn.append({"type": "tool_result", "tool_use_id": skipped_block.id, "content": f"Not executed — {skip_reason}."})
            messages.append({"role": "user", "content": tool_results_this_turn})
            
            if case_terminated:
                return final_result

if __name__ == "__main__":
    import asyncio
    import anthropic

    anthropic_client = anthropic.Anthropic()
    claude_model_name = "claude-haiku-4-5-20251001"

    case = {
        "id": "test-1",
        "text": "I was charged twice for invoice #7734 — same amount, same date, two separate charges on my card statement. Can you refund the duplicate?",
        "customer_tier": "pro",
        "previous_ticket_count": 0,
    }
    async def _test():
        server_params = StdioServerParameters(command="python", args=["src/mcp_server.py"])
        async with Client(server_params) as client:
            result = await run_agent_on_case_mcp(case, client, anthropic_client, claude_model_name)
            print(json.dumps(result, indent=2))
    asyncio.run(_test())
    