# Synthetic Ticket Dataset — Spec

## Purpose

A hand-written synthetic dataset used to build and evaluate the triage agent. Each ticket is
labeled with an **expected outcome before the agent runs**, so evaluation is a mechanical
comparison, not a judgment call made after the fact.

## Category taxonomy

Six categories, each designed to stress a specific part of the system. Not all are built in v1
— see "Build order" below.

| # | Category | What it stresses | Built in v1? |
|---|---|---|---|
| 1 | Category-ambiguous | Model's classification, Layer 1 rule applicability | No — later |
| 2 | Near-miss retrieval | Layer 2 similarity threshold, tuning `T` | No — later |
| 3 | Confidence-contradiction | Layer 3 as a real tie-breaker, not rubber-stamp | No — later |
| 4 | Loop-bait | Max-iteration guard, repeat-call guard | No — later |
| 5 | Hard-rule collision | Layer 1 precedence — does it pull real weight? | **Yes** |
| 6 | Clean baseline | Happy path, sanity check before trusting adversarial results | **Yes** |

### Category definitions

**1 — Category-ambiguous:** Ticket plausibly belongs to two categories at once (e.g. "charged
for a feature that doesn't work" — billing or technical). Tests whether the model commits to one
category and whether Layer 1 rules are well-defined when the "true" category is debatable.

**2 — Near-miss retrieval:** Knowledge base has content that's related but doesn't actually
answer the question (e.g. general refund policy doc vs. a specific duplicate-charge question).
Similarity score lands in the ambiguous middle — this is where the threshold `T` gets tested for
real, not just guessed at.

**3 — Confidence-contradiction:** Retrieval similarity passes Layer 2, but the answer is subtly
wrong or incomplete. Tests whether self-reported confidence (Layer 3) ever catches what
similarity missed, or just rubber-stamps a mediocre retrieval.

**4 — Loop-bait:** Ticket phrased vaguely enough that a first `search_knowledge_base` call
plausibly returns something unhelpful, tempting a retry with rephrased queries. Tests whether
the repeat-call guard actually fires.

**5 — Hard-rule collision:** Ticket is billing-related (Layer 1 rule: never auto-resolve) *and*
has weak retrieval similarity *and* the model self-reports low confidence — all three layers
agree independently. Sanity check: is Layer 1 pulling real weight, or would Layers 2+3 have
caught it anyway?

**6 — Clean baseline:** Unambiguous in every dimension — clear category, clear urgency,
obviously resolvable or obviously not. Establishes a known-good baseline so failures on
adversarial cases can be trusted as real bugs, not noise in a system that never worked.

## Build order

**v1 seed set:** Categories 5 and 6 only, ~3-4 tickets each (~6-8 total). Rationale: these
answer the most important early question — does the loop run correctly, and do the confidence
layers actually do something, even in the simplest cases? A bug in category 5 (e.g. a billing
ticket somehow gets auto-resolved) is a core mechanism failure; no value in adding categories
1-4 until that's ruled out.

**Post-v1:** Add categories 1-4 once the core loop is verified against the seed set.

## Ticket schema

```json
{
  "id": "string, unique",
  "text": "free-text ticket body",
  "customer_tier": "free | pro | enterprise",
  "previous_ticket_count": 0,
  "category_hint": "which taxonomy category (5 or 6) this ticket belongs to — for your own tracking, not seen by the agent",
  "expected": {
    "expected_action": "resolve | route | escalate",
    "expected_category_blocks_resolve": true,
    "why": "human-written justification, used for evaluation, written BEFORE running the agent"
  }
}
```

## Evaluation procedure

1. Write all seed tickets with `expected` filled in first — no peeking at agent output first.
2. Run every ticket through the agent, capture the full structured trace.
3. Compare `final_action` (from the trace) to `expected.expected_action`.
4. For category 5 specifically: confirm `expected_category_blocks_resolve` was actually enforced
   at Layer 1, not accidentally passed through to Layers 2/3.
5. Any mismatch is a bug to diagnose using the structured trace — not a reason to loosen the
   expected label after the fact.

## Knowledge base note

The existing RAG pipeline's document set (e.g. general reference PDFs from the prior project)
will not produce meaningful similarity scores for support-ticket-style questions. Before running
evaluation, swap in documents that could plausibly answer at least some tickets and confidently
fail to answer others (e.g. a billing FAQ, a basic technical troubleshooting doc) — this is a
data change only, not a pipeline change, since the existing extraction/chunking/embedding code
is format-agnostic.
