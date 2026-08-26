"""
Tests for src/trace.py.

Each test below maps to something you already verified manually in
learn/scripts/scratch_trace.py. Formalizing it here means it can be re-run
automatically (via `pytest` from the project root) instead of re-reading
printed output by eye each time.

Run with: pytest tests/test_trace.py -v
(the -v flag shows each test's name and pass/fail individually)
"""

import pytest
from src.trace import CaseTrace, make_step_record


def test_make_step_record_builds_expected_shape():
   
    # ARRANGE — decide what inputs you're going to pass in
    step_number = 1
    step_type = "tool_call"
    name = "search_knowledge_base"
    details = {"top_similarity": 0.5}

    # ACT — call the actual function with those inputs
    record = make_step_record(step_number, step_type, name, details)

    # ASSERT — check the output matches what you expect
    assert record["step_number"] == step_number
    assert record["step_type"] == step_type
    assert record["name"] == name
    assert record["details"] == details
     
   
def test_add_step_appends_to_steps_list():
    """
    Create a CaseTrace, build one record with make_step_record, call add_step.
    Assert the record actually landed in trace.steps — and specifically that
    it's the exact same dict, not a tuple or something mangled (this is the
    bug you caught earlier with *args, **kwargs — worth locking in a test
    that would have caught it).
    """
    step_number = 1
    step_type = "tool_call"
    name = "search_knowledge_base"
    details = {"top_similarity": 0.5}
    
    record = make_step_record(step_number, step_type, name, details)
    trace = CaseTrace(case_id="test_1")
    trace.add_step(record)

    assert len(trace.steps) == 1
    assert trace.steps[0] == record


def test_add_step_preserves_order_across_multiple_calls():
    """
    Add two or three records in a specific order. Assert trace.steps reflects
    that same order (step_number 1, then 2, then 3 — not scrambled).
    """
    step_number_1 = 1
    step_type_1 = "tool_call"
    name_1 = "search_knowledge_base"
    details_1= {"top_similarity": 0.5}
        
    
    step_number_2 = 2
    step_type_2 = "rule_check"
    name_2 = "billing_no_resolve"
    details_2 = {"result": "blocked_resolve"}
    
    record1 = make_step_record(step_number_1, step_type_1, name_1, details_1)
    record2 = make_step_record(step_number_2, step_type_2, name_2, details_2)
    
    trace = CaseTrace(case_id="test_1")
    trace.add_step(record1)
    trace.add_step(record2)

    assert len(trace.steps) == 2
    assert trace.steps[0] == record1
    assert trace.steps[1] == record2

def test_set_final_action_stores_value():
    """
    Create a CaseTrace, call set_final_action once. Assert final_action was
    actually stored correctly.
        """
    final_action = "resolve"
    trace = CaseTrace(case_id="test_2")
    trace.set_final_action(final_action)
   
    assert trace.final_action == final_action


def test_set_final_action_raises_on_second_call():
    """
    Call set_final_action once (should succeed), then call it again with a
    DIFFERENT value (mirrors your scratch script's "escalate" then "route").
    Use pytest.raises(ValueError) to assert the second call fails.

    Bonus: after the failed second call, assert final_action STILL holds the
    original value, not the attempted second one — proving the guard didn't
    partially corrupt state before raising.
    """
    trace = CaseTrace(case_id="test_3")
    trace.set_final_action("resolve")
    with pytest.raises(ValueError):
         trace.set_final_action("escalate")
    
    assert trace.final_action == "resolve"


def test_to_dict_reflects_full_state():
    """
    Build a CaseTrace with a couple of steps and a final_action set. Call
    to_dict(). Assert the returned dict's case_id, steps, and final_action
    all match what you put in — this is the end-to-end check that ties
    together everything the other tests verified individually.
    """
    step_number_1 = 1
    step_type_1 = "tool_call"
    name_1 = "search_knowledge_base"
    details_1= {"top_similarity": 0.5}
            
    step_number_2 = 2
    step_type_2 = "rule_check"
    name_2 = "billing_no_resolve"
    details_2 = {"result": "blocked_resolve"}
        
    record1 = make_step_record(step_number_1, step_type_1, name_1, details_1)
    record2 = make_step_record(step_number_2, step_type_2, name_2, details_2)
        
    trace = CaseTrace(case_id="test_1")
    trace.add_step(record1)
    trace.add_step(record2)
    trace.set_final_action("escalate")
    with pytest.raises(ValueError):
             trace.set_final_action("resolve")
    result = trace.to_dict()
    
    assert result["case_id"] == "test_1"
    assert result["steps"][0] == record1
    assert result["steps"][1] == record2
    assert result["final_action"] == "escalate"
    
 

def test_to_dict_before_final_action_set_does_not_crash():
    """
    Create a CaseTrace, add a step, but DON'T call set_final_action. Call
    to_dict() anyway. Assert it doesn't raise an error, and that
    final_action in the returned dict is None — this is the placeholder-value
    design decision from __init__ actually being exercised, not just assumed
    safe.
    """
    step_number_1 = 1
    step_type_1 = "tool_call"
    name_1 = "search_knowledge_base"
    details_1= {"top_similarity": 0.5}
    record1 = make_step_record(step_number_1, step_type_1, name_1, details_1)
    trace = CaseTrace(case_id="test_2")
    trace.add_step(record1)
    result_1 = trace.to_dict()

    assert result_1["case_id"] == "test_2"
    assert result_1["steps"][0] == record1
    assert result_1["final_action"] is None