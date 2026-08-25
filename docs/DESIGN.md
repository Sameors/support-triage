# Support/Case Triage Agent — Design Doc (v1.1)

**Status:** Scoped, not yet built
**Author:** [your name]
**Predecessor project:** Document Q&A RAG (PDF/DOCX/TXT → chunk → embed → ChromaDB → Claude Haiku → Streamlit)
**Revision note:** v1.1 patches structural gaps found in review of v1 — see §12 for a changelog.

---

## 1. Purpose

A deliberately smaller, self-built analogue of agentic case-assignment systems (the kind Pega
Infinity '26 ships via MCP-based agents). The goal is **not** a production triage tool — it's a
learning vehicle for tool-calling and reasoning-loop mechanics: a model that decides its own
sequence of actions at runtime, rather than executing a fixed pipeline.

The predecessor RAG project was a **fixed pipeline** — same five stages, every input, no
branching, no decisions. This project introduces **model-driven branching**: given an incoming
support case, the agent decides — for itself, mid-conversation — whether to search a knowledge
base, route the case to a queue, or escalate to a human, and can change course based on what it
finds.

## 2. Explicit relationship to Pega background

- Pega is used here as **conceptual inspiration only.** No integration, no Pega API calls, no
  Pega Platform involvement anywhere in this build.
- Instincts borrowed from Pega decisioning/case management (rule-gating before scoring,
  structured audit trails, fixed routing destinations) are deliberately reused — these transfer
  as design patterns, not as code.
- This project uses **raw Anthropic API tool-use**, not MCP. It teaches the underlying
  tool-calling mechanic that MCP standardizes, but not the MCP protocol itself (client/server,
  resource discovery, transport). MCP is an explicit v3 follow-on, not part of this build.
- This project is a **single-shot triage decision**, not a full case lifecycle. Pega case types
  have stages, SLA timers, and state that persists over time; this agent takes one ticket in and
  produces one trace out. Case lifecycle/staging is an explicit v2 follow-on.

## 3. Functional requirements

The agent, given one case as input, must:

1. **Classify** the case's category and urgency **before any other decision is reachable** (see
   §4, Step 0). No downstream rule, tool, or action executes against an unclassified case.
2. **Decide** one final action: `resolve`, `route`, or `escalate` — via a tool-calling reasoning
   loop, not a single classification call.
3. If attempting resolution, **call the existing RAG pipeline** (wrapped as a tool) and evaluate
   whether the result is good enough to act on, then **explicitly propose resolution** via a
   dedicated tool call that triggers the gating check (see §6, `propose_resolution`).
4. **Apply hard-rule gates** before any resolution is allowed (see §5).
5. **Log a structured, step-by-step trace** of every tool call, input, output, and the final
   action — sufficient to audit *why* a decision was made without trusting model-generated prose
   as the source of truth.
6. **Terminate** within a bounded number of reasoning steps, never looping indefinitely.

## 4. Architecture: tool-calling reasoning loop

This is **not** "one classification call, code branches" (that would just be the old RAG
pipeline with an `if/else`). This is a real agent loop:

```
Step 0 (enforced in code, not by prompt instruction alone):
  The first tool call the model makes MUST be classify_case, with one exception —
  escalate remains legal as an always-available bailout from turn 1, since a case may
  be malformed or unsafe to process at all.
  If the model's first tool call is anything else, reject it: return a tool_result
  stating classification is required first, and re-prompt. Do not proceed to Step 1
  until classify_case has been recorded in loop state.

Step 1 (main loop, after classification exists):
  1. Send case + conversation so far + tool definitions to the model.
  2. Read stop_reason.
     - If "tool_use": extract tool name + input, execute it yourself (your code, not the
       model), append the real result back into the conversation as a tool_result, go to
       step 1.
     - If anything else: loop ends, read the model's final action from its last tool call.
  3. Guard rails, checked every iteration:
     - max_iterations (e.g. 5) — exceeded → force action = "escalate",
       reason = "exceeded reasoning steps"
     - repeat_call_guard — same tool called twice CONSECUTIVELY, regardless of input,
       is treated as a stuck signal. This is a coarse heuristic, not a precise
       stuck-detector: exact-input matching was considered and rejected, since
       non-deterministic model phrasing rarely repeats exactly (same underlying
       failure mode as unreliable exact-match refusal detection noted in prior
       project). max_iterations remains the real backstop; this guard just may fire
       earlier in obvious cases.
```

Implementation: hand-written `while` loop around the raw Anthropic `/v1/messages` API.
**No framework** (LangGraph, etc.) for v1 — a framework would abstract away exactly the mechanic
this project exists to teach. Revisit post-v1 as a deliberate "port to a framework" exercise.

## 5. Confidence model (3 layers, checked in order)

Model self-reported confidence is not reliably correlated with correctness — a model can sound
90% confident about a hallucinated or weakly-grounded answer. Confidence is therefore layered,
with earlier layers overriding later ones. **All three layers read from loop state written by
explicit tool calls — never from parsing model prose.**

**Layer 1 — Hard rules (non-negotiable, plain Python, not a prompt instruction)**
- Reads `category` and `urgency` from the `classify_case` result recorded in Step 0. Since
  classification is now mandatory before any other decision, this layer is always checkable —
  it can no longer be skipped or bypassed by an unclassified case reaching resolution logic.
- Category in `{billing, legal, refund}` → resolve is blocked, regardless of anything else.
- Urgency == `critical` → resolve is blocked, regardless of anything else.

**Layer 2 — Retrieval-grounded (measured, not asked)**
- If `search_knowledge_base` is called, the tool returns `top_similarity` (real ChromaDB
  similarity score, not a model opinion), recorded in loop state.
- Below threshold `T` (value TBD via testing against the seed dataset — see §9) → resolve is
  blocked.

**Layer 3 — Self-reported score (tie-breaker only, weakest signal)**
- Only consulted if Layers 1 and 2 both pass.
- If the model's self-reported confidence disagrees sharply with a passing Layer 2 score, that
  mismatch itself is logged and treated as an escalation trigger, not just noise.

Non-critical urgency levels (`low`/`medium`/`high`) are classified and logged but do **not**
currently affect any decision. Do not add threshold-tuning behavior for them until testing shows
a concrete failure case that requires it — avoid designing against a hypothetical.

## 6. Tools

### `classify_case(category: enum, urgency: enum)`
- **Mandatory first tool call** (see §4, Step 0). Not optional, not inferred from later prose.
- `category`: enum `{billing, legal, refund, technical, account, general}`.
- `urgency`: enum `{low, medium, high, critical}`.
- Result is written directly into loop state. Layer 1 (§5) reads from this state, not from
  re-parsing anything the model says later in the conversation.

### `search_knowledge_base(query: str)`
- Wraps the **existing** RAG pipeline (embeddings + ChromaDB retrieval + generation). Reused
  as-is — no rewrite of chunking, embedding, or retrieval logic.
- New work is limited to: (a) a thin adapter reshaping the existing function's output into the
  structured return below, (b) the tool schema itself.
- Returns structured data, not just prose, because Layer 2 confidence depends on it:
  ```json
  {
    "answer": "...",
    "top_similarity": 0.41,
    "chunks_used": ["...", "..."]
  }
  ```

### `route_to_queue(queue: enum, reason: str)`
- `queue` is a **fixed enum** defined in the tool schema (e.g. `billing`, `technical`,
  `account`, `general`) — not open-ended text. The model must land in a real bucket.

### `propose_resolution(answer: str, based_on_similarity: float)`
- **This is the only mechanism by which the model signals intent to resolve.** Calling it does
  not resolve the case by itself — it triggers your code to run the Layer 1 → 2 → 3 pipeline
  (§5) against current loop state (classification already recorded from Step 0; `top_similarity`
  already recorded if `search_knowledge_base` was called).
- **If all layers pass:** `final_action = resolve`. Output is the draft `answer`, marked
  `pending_human_approval = true`. Never auto-sent to a customer in v1.
- **If any layer fails:** the tool_result returned to the model states which layer blocked it
  (e.g. `"blocked: category=billing, hard rule"`), and the model must choose its next move —
  `route_to_queue`, `escalate`, or another `search_knowledge_base` call if it believes the block
  was based on insufficient evidence — bounded by `max_iterations` regardless.
- This replaces v1's ambiguous "resolve is an outcome, not a tool" language — resolution is now
  an explicit, gated decision the model makes and the system verifies, not a state your
  evaluation code has to infer after the fact.

### `escalate(reason: str)`
- **Log-only in v1.** Sets `final_action = "escalate"`, writes to the structured trace.
  Nothing is delivered (no Slack, no email, no notification). Delivered escalation is an
  explicit follow-on, not built until the reasoning underneath it is verified trustworthy.
- Remains legal at any point in the loop, including turn 1 (before classification), as the
  system's universal safe bailout.

## 7. Logging / audit trail

Two distinct things, not conflated:

- **Structured step-trace (source of truth):** ordered list of `{step, type, tool, input,
  output, result}` records — queryable, not just readable. This is what an audit trail actually
  requires; prose alone cannot answer "show me every case where similarity was under 0.4 but the
  agent still tried to resolve."
- **Model rationale (attached, not trusted):** the model's free-text explanation, kept for
  context but never treated as ground truth — it's a plausible-sounding explanation, not
  verified evidence.

Example shape:

```json
{
  "case_id": "1024",
  "steps": [
    {"step": 0, "type": "tool_call", "tool": "classify_case",
     "input": "...", "result": {"category": "billing", "urgency": "medium"}},
    {"step": 1, "type": "rule_check", "result": "blocked_resolve", "rule": "category=billing"},
    {"step": 2, "type": "tool_call", "tool": "search_knowledge_base",
     "input": "...", "top_similarity": 0.41},
    {"step": 3, "type": "tool_call", "tool": "escalate", "input": {"reason": "..."}}
  ],
  "final_action": "escalate",
  "model_rationale": "..."
}
```

The schema above should be treated as a first draft, not final — expect at least one revision
once §9's invariant checks are written and surface a field you need that isn't captured yet.

## 8. Input data

Synthetic dataset (no real ticket ingestion in v1). Each case:

```json
{
  "text": "free-text ticket body",
  "expected": {
    "expected_action": "resolve | route | escalate",
    "expected_category": "billing | legal | refund | technical | account | general",
    "why": "human-written justification, used for evaluation"
  }
}
```

**Explicitly excluded fields:**
- `product_area`/pre-supplied category — handing the model a category would pre-solve the
  classification step and turn the test into confirming a label rather than deriving one.
- `customer_tier` and `previous_ticket_count` — cut from v1 entirely. These were present in the
  original draft schema but referenced by no rule, tool, or confidence layer. An unused field in
  the case object is a silent invitation for the model to reason over a signal your eval harness
  never checks — worse than the field simply not existing. **v2 follow-on:** reintroduce
  `customer_tier` with an explicit rule (e.g., enterprise tier tightens the Layer 2 threshold),
  not before.

See `DATASET.md` for the full seed set and category taxonomy.

## 9. Evaluation

Not "read the trace and see if it looks right" — that's the same ungrounded-confidence problem
rejected for the model in §5, just performed manually instead. Each seed case is labeled with an
**expected outcome before the agent ever sees it.**

Evaluation runs in two passes, checked separately and reported separately:

**Pass 1 — Outcome match (as v1 originally specified)**
- Run all cases, compare `final_action` to `expected.expected_action`. Count matches/mismatches.

**Pass 2 — Trace invariants (new in v1.1)**
- An outcome-correct case can still have gotten there through a broken mechanism — e.g. a bug
  that resolves a billing case without Layer 1 ever firing, which Pass 1 alone would silently
  count as a pass. Pass 2 catches this:
  - If `expected.expected_category` ∈ `{billing, legal, refund}`: trace must contain a
    `rule_check` step with `result = blocked_resolve`.
  - If `final_action = resolve`: trace must contain a `search_knowledge_base` call with
    `top_similarity ≥ T`, and a `propose_resolution` call that passed all three layers.
  - If `final_action = escalate` specifically due to Layer 3 disagreement: trace must log the
    self-report/Layer-2 mismatch explicitly (per §5, Layer 3).
- A case that passes Pass 1 but fails Pass 2 is a **false-positive-correct** result: log it as a
  bug, not as a pass. This is the check that prevents "right answer, wrong reason" from
  silently clearing the eval harness.

Dataset composition should deliberately include cases near the Layer 2 threshold boundary (not
just clear-cut similarity scores) and at least one case requiring 4–5 reasoning steps, since `T`
and `max_iterations` can only be tuned meaningfully against cases that actually stress them.

## 10. Out of scope (v1)

- Real ticket ingestion (email, Zendesk, etc.) — synthetic dataset only
- Delivered escalation notifications (Slack/email) — log-only
- Case lifecycle, staging, SLA timers, persistence across time — single-shot per ticket
- MCP protocol — raw Anthropic tool-use only
- Agent frameworks (LangGraph, etc.) — hand-written loop only
- Auto-sending resolutions to customers — draft + human approval always required
- Multi-turn conversation with the customer — one ticket in, one trace out
- Fine-tuning — same prompted Claude model as the RAG project
- `customer_tier` / `previous_ticket_count`-based logic — field cut entirely, see §8

## 11. Explicit follow-ons (not v1, sequenced deliberately)

- **v2:** Case lifecycle — persistent state, stages, SLA-timer-driven re-escalation. Also where
  `customer_tier` gets reintroduced, with an explicit rule attached. Builds on top of a working
  v1 without touching the tool-calling mechanics.
- **v3:** Re-platform the same tools behind an actual MCP server/client, specifically to learn
  the protocol Pega uses. Deliberately sequenced *after* v1 so the underlying mechanic is
  already understood before adopting the standardized wrapper around it.

## 12. Changelog from v1

- Added §4 Step 0: `classify_case` is now a code-enforced mandatory first call, closing the gap
  where Layer 1 hard rules had nothing guaranteed to check against.
- Added `propose_resolution` tool (§6): resolution is now an explicit, gated tool call rather
  than an inferred state, closing the gap where "resolve" had no concrete trigger mechanism.
- Reframed `repeat_call_guard` (§4) to match on consecutive tool name rather than exact input,
  and documented it honestly as a coarse heuristic rather than a precise stuck-detector.
- Cut `customer_tier` / `previous_ticket_count` from the input schema (§8) since neither was
  wired into any rule or tool; moved to an explicit v2 follow-on instead of sitting unused.
- Added Pass 2 (trace invariants) to evaluation (§9) to catch outcome-correct-but-mechanism-wrong
  results that the original match/mismatch check would have silently passed.
