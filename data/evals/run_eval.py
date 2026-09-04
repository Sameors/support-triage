import json
from pathlib import Path
from src.agent_loop import run_agent_on_case, infrastructure
from data.evals.checks import check_pass_1 , check_pass_2 , print_eval_table

dataset_path = Path(__file__).parent / "eval_dataset.json"
with open(dataset_path, "r") as f:
    dataset = json.load(f)

combined_results = []
for case in dataset:
    result = run_agent_on_case(case, infrastructure)
    p1 = check_pass_1(case, result)
    p2 = check_pass_2(case, result)
    combined_results.append({
        "case_id": case["id"],
        "pass_1": p1,
        "pass_2": p2,
    })
print_eval_table(combined_results)

    # print(p1)  # temporary — replace with real table later
    # results.append({"case_id": case["id"], "pass_1": p1})