"""
Structured trace for the triage agent.

Design reference: DESIGN.md §7

Purpose: every tool call, rule check, and final action for a single case gets
recorded as one entry in an ordered list. This is the audit trail — it must be
queryable (e.g. "find every case where a rule_check blocked resolve"), not just
a paragraph of prose.

Two kinds of step exist:
  - "tool_call"  — the model called a tool (classify_case, search_knowledge_base,
                    propose_resolution, route_to_queue, escalate), your code
                    executed it, here is what happened.
  - "rule_check" — your OWN code evaluated something (e.g. a Layer 1 hard rule)
                    without the model being involved at all. This is what lets
                    Pass 2 evaluation (DESIGN.md §9) verify a decision was reached
                    through the correct mechanism, not just the correct outcome.

"""

from typing import Any, Literal


# ---------------------------------------------------------------------------
# A single entry in a case's trace.
# ---------------------------------------------------------------------------

def make_step_record(
    step_number: int,
    step_type: Literal["tool_call","correction","error","timeout_escalate"],
    name: str,
    details: dict[str, Any]
) -> dict[str, Any]:
    """
    Build one step record for the trace.
    """
    return {
            "step_number" : step_number,
            "step_type" : step_type,
            "name" : name,
            "details" :details     
    }


# ---------------------------------------------------------------------------
# The full trace for one case, start to finish.
# ---------------------------------------------------------------------------

class CaseTrace:
    """
    Accumulates step records for a single case as the agent loop runs, then
    exposes the finished trace for logging/evaluation.
    """

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.steps = []
        # TODO: revisit once tools.py clarifies whether model_rationale needs its own field
        self.final_action = None

    def add_step(self, record: dict[str, Any]) -> None:
        """
        Append one step record. Signature is up to you — but every caller
        (each tool function, the loop's rule-check logic) should be able to
        call this the same way, without special-casing step_type.
        """
        self.steps.append(record)

    def set_final_action(self, action: Literal["resolve", "route", "escalate"]) -> None:
        """
        Record the terminal action once the loop ends. Called exactly once,
        from exactly one place
        """
        if self.final_action is None:
            self.final_action = action 
        else:
            raise ValueError(
                    f"final_action already set to '{self.final_action}' for case {self.case_id}; "
                    f"cannot set it to '{action}'"
)
        
    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the full trace to the shape that gets written to disk /
        compared against expected labels during evaluation. Cross-check this
        against DATASET.md's evaluation procedure before finalizing the shape.
        """
        return {
            "case_id" : self.case_id,
            "steps" : self.steps,
            "final_action" : self.final_action
        }
