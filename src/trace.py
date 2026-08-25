"""
Structured trace for the triage agent.

Design reference: DESIGN.md §7 (Logging / audit trail), §9 (Evaluation — Pass 2).

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

YOU decide: dataclass vs. TypedDict vs. plain dict. Whatever you pick, every
function elsewhere in this project that writes to the trace should use this
shape consistently — decide it here once, don't let each tool invent its own
record format.
"""

from typing import Any, Literal


# ---------------------------------------------------------------------------
# A single entry in a case's trace.
# ---------------------------------------------------------------------------

def make_step_record(
    step_number: int,
    step_type: Literal["tool_call", "rule_check"],
    # TODO: what other fields does a step need to be independently useful
    # when read on its own, out of context? Look back at DESIGN.md §7's
    # example shape for a starting point — but ask yourself if it's complete.
    # e.g.: does a "tool_call" step need different fields than a "rule_check"
    # step? Should this be one function or two?
) -> dict[str, Any]:
    """
    Build one step record for the trace.

    Must contain enough information that Pass 2 evaluation (DESIGN.md §9) can
    answer questions like:
      - "Did a rule_check with result=blocked_resolve occur before this case's
         final_action was set?"
      - "What was top_similarity when search_knowledge_base was called?"
    without re-deriving that information from anywhere else.

    Returns:
        A single record, shape TBD by you.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# The full trace for one case, start to finish.
# ---------------------------------------------------------------------------

class CaseTrace:
    """
    Accumulates step records for a single case as the agent loop runs, then
    exposes the finished trace for logging/evaluation.

    Think about:
      - What does the loop need to call on this object at EVERY iteration,
        regardless of which tool fired? (append something, presumably —
        what's the minimal interface?)
      - What does this object need to hold once the loop ends, so evaluation
        (Pass 1 AND Pass 2 from DESIGN.md §9) can run against it without
        re-parsing raw API responses?
      - case_id, the list of step records, final_action, and model_rationale
        are the fields named in DESIGN.md §7's example — is that list actually
        complete, or did writing propose_resolution's gating logic (coming
        next) surface something else this needs to hold?
    """

    def __init__(self, case_id: str):
        # TODO
        raise NotImplementedError

    def add_step(self, *args, **kwargs) -> None:
        """
        Append one step record. Signature is up to you — but every caller
        (each tool function, the loop's rule-check logic) should be able to
        call this the same way, without special-casing step_type.
        """
        raise NotImplementedError

    def set_final_action(self, action: Literal["resolve", "route", "escalate"]) -> None:
        """
        Record the terminal action once the loop ends. Called exactly once,
        from exactly one place — where in the loop should that be, and what
        should happen if something tries to call this twice?
        """
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the full trace to the shape that gets written to disk /
        compared against expected labels during evaluation. Cross-check this
        against DATASET.md's evaluation procedure before finalizing the shape.
        """
        raise NotImplementedError
