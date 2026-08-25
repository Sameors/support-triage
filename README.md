# Support/Case Triage Agent

**Status:** In development — design scoped, `src/trace.py` in progress.

A tool-calling reasoning-loop agent that classifies incoming support tickets and
decides, at runtime, whether to resolve them via a reused RAG pipeline, route them
to a queue, or escalate to a human — with every decision logged in a structured,
auditable trace.

Built as a learning project on tool-calling and agentic reasoning-loop mechanics,
following on from a deterministic Document Q&A RAG pipeline (fixed pipeline, no
branching). See [`docs/DESIGN.md`](docs/DESIGN.md) for the full design doc,
including architecture, confidence model, and explicit scope boundaries, and
[`docs/DATASET.md`](docs/DATASET.md) for the synthetic ticket taxonomy and
evaluation approach.

## Status / progress

- [x] Design scoped (`docs/DESIGN.md`, `docs/DATASET.md`)
- [ ] `src/trace.py` — structured trace data shape
- [ ] `src/tools.py` — five tool functions + schemas
- [ ] `src/agent_loop.py` — the reasoning loop
- [ ] `data/tickets.json` — seed dataset (categories: hard-rule collision + baseline)
- [ ] First end-to-end run
- [ ] Evaluation (Pass 1: outcome match, Pass 2: mechanism match)

<!-- Full setup instructions, architecture diagram, screenshots, and known
     limitations go here once the project is functional — not before. -->
