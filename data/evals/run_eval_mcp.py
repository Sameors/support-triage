import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.evals.checks import check_pass_1 , check_pass_2 , print_eval_table
from mcp import Client, StdioServerParameters
from src.mcp_agent_loop import run_agent_on_case_mcp
import time
import asyncio  
import json
import anthropic

async def run_eval(dataset, anthropic_client, claude_model_name):
    server_params = StdioServerParameters(command="python", args=["src/mcp_server.py"])
    async with Client(server_params) as client:
        combined_results = []
        for case in dataset:
            start = time.time()
            result = await run_agent_on_case_mcp(case,client, anthropic_client, claude_model_name)
            p1 = check_pass_1(case, result)
            p2 = check_pass_2(case, result)
            combined_results.append({
                    "case_id": case["id"],
                    "pass_1": p1,
                    "pass_2": p2,
                })
            print(f"[{case['id']}] done in {time.time() - start:.1f}s — final_action: {result['final_action']}")
            
    return combined_results

if __name__ == "__main__":
    dataset_path = Path(__file__).parent.parent.parent / "data" / "evals" / "eval_dataset.json"
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
    anthropic_client = anthropic.Anthropic()
    claude_model_name = "claude-haiku-4-5-20251001"
    combined_results = asyncio.run(run_eval(dataset, anthropic_client, claude_model_name))
    print(f"===========Using MCP=====================")
    print_eval_table(combined_results)
