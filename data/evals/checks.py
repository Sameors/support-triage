def check_pass_1(case: dict, result: dict) -> dict:
      
    """
    Returns something like {"status": "pass"|"fail"|"error", "expected": ..., "actual": ...}
    """
    if result["final_action"] == "error":
        return {
            "case_id": case["id"],
            "status": "error",
            "expected": None,
            "actual": None,
            "guard_fired": None,
            "error_type": result["error_type"],
            "error_message": result["error_message"],
                }
    if any(step["step_type"] == "duplicate_toolcall" for step in result["trace"]["steps"]):
        expected_value = case["guard_triggered_final_action"]
        actual_value = result["final_action"]
        return {
            "case_id": case["id"],
            "status": "pass" if actual_value == expected_value else "fail",
            "expected": expected_value,
            "actual": actual_value,
            "guard_fired": True,
            "error_type": None,
            "error_message": None,
                }
    else:
        expected_value = case["expected_final_action"]
        actual_value = result["final_action"]
        return {
                "case_id": case["id"],
                "status": "pass" if actual_value == expected_value else "fail",
                "expected": expected_value,
                "actual": actual_value,
                "guard_fired": False,
                "error_type": None,
                "error_message": None,
                }

def is_subsequence(expected: list, actual: list) -> bool:
    expected_idx = 0
    for item in actual:
        if expected_idx < len(expected) and item == expected[expected_idx]:
            expected_idx += 1
    return expected_idx == len(expected)

def check_pass_2(case: dict, result: dict) -> dict:
    
    actual_sequence = [step["name"] for step in result["trace"]["steps"] if step["step_type"] == "tool_call"]
    is_subsequence_match = is_subsequence(case["expected_tool_sequence"],actual_sequence)
    sequence_status = "pass" if is_subsequence_match else "fail"
    
    if case["check_layers"] is False:
        layer_check_applicable = False
        layer_status = None
    else:
        layer_check_applicable = True
        layer_status = "fail"
        for step in result["trace"]["steps"]:
            if step["step_type"] == "tool_call" and step["name"] == "propose_resolution":
                l1_ok = layer_matches(step["details"]["layer_1"], case["expected_layers"]["layer_1"])
                l2_ok = layer_matches(step["details"]["layer_2"], case["expected_layers"]["layer_2"])
                l3_ok = layer_matches(step["details"]["layer_3"], case["expected_layers"]["layer_3"])
                layer_status = "pass" if (l1_ok and l2_ok and l3_ok) else "fail"
                break
    return {
    "case_id": case["id"],
    "sequence_status": sequence_status,
    "expected_sequence": case["expected_tool_sequence"],
    "actual_sequence": actual_sequence,
    "layer_check_applicable" : layer_check_applicable,
    "layer_status" : layer_status  
    }

def layer_matches(actual_layer, expected_value: str | None) -> bool:
    actual_value = actual_layer["resolve"] if actual_layer is not None else None
    return actual_value == expected_value

def print_eval_table(combined_results: list[dict]) -> None:
    def print_rows(rows):
        header = f"{'case_id':<28} {'pass_1':<7} {'seq':<7} {'layer':<7}"
        print(header)
        print("-" * len(header))
        for r in rows:
            p1_status = r["pass_1"]["status"]
            seq_status = r["pass_2"]["sequence_status"]
            layer_status = r["pass_2"]["layer_status"] if r["pass_2"]["layer_check_applicable"] else "n/a"
            print(f"{r['case_id']:<28} {p1_status:<7} {seq_status:<7} {layer_status:<7}")
    print_rows(combined_results)
   
    failures = [
        r for r in combined_results
        if r["pass_1"]["status"] != "pass"
        or r["pass_2"]["sequence_status"] != "pass"
        or (r["pass_2"]["layer_check_applicable"] and r["pass_2"]["layer_status"] != "pass")
    ]
    if failures:
        print("\n--- Failures only ---")
        print_rows(failures)
    total = len(combined_results)
    gate1 = sum(1 for r in combined_results if r["pass_1"]["status"] == "pass")
    gate2 = sum(1 for r in combined_results if r["pass_2"]["sequence_status"] == "pass")
    gate3 = sum(1 for r in combined_results if r["pass_2"]["layer_status"] == "pass")
    gate3_applicable = sum(1 for r in combined_results if r["pass_2"]["layer_check_applicable"])
    print(f"\nPass 1: {gate1}/{total} passed")
    print(f"Pass 2 (sequence): {gate2}/{total} passed")
    print(f"Pass 2 (layers): {gate3}/{gate3_applicable} passed ({total - gate3_applicable} not applicable)")