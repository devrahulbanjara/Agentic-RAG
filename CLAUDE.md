# Project Guide

Project guide. Read once at session start. Defer deep spec to `example.md`.

## Project

**Production-grade agentic RAG over arXiv papers.** Two-stage pipeline: offline indexing (parse → chunk → enrich → embed → store), runtime inference (classify → retrieve → rerank → generate). Continuously evaluated, stress-tested for adversarial inputs.

- Corpus scope v1: 500–2000 papers (approximate), `cs.CL` / `cs.LG` / `cs.CV`.
- Full architecture rendered: `docs/assets/architecture.png`.

## Stack

Tech stack and coding standards as of 2026:

- Python 3.14, FastAPI, Pydantic v2, SQLAlchemy, Alembic, `uv` for dep mgmt.
- Postgres 16 (source of truth), Qdrant (vector + sparse index).
- Airflow DAGs.
- Embeddings: BGE-M3 (1024-d dense + sparse, one model). Reranker: BGE-reranker-v2-m3.
- Docling (PDF parse) + GROBID (reference extraction).

My current goal is to reach a certain milestone and then only use Airflow, and other tools as needed. For now I am focusing on building the core functionality, by manually downloading papers and running the indexing pipeline.

## Finish checklist

If you touched anything:

- `uvx ruff check --fix && uvx ruff format`
- Don't commit unless asked.

---

# Behavioral guidelines

Bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think before coding

- State assumptions explicitly. If uncertain, ask.
- Multiple interpretations exist → present them, don't pick silently.
- Simpler approach exists → say so. Push back when warranted.
- Unclear → stop, name the confusion, ask.

## 2. Simplicity first

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No flexibility/configurability that wasn't requested.
- No error handling for impossible scenarios.
- 200 lines that could be 50 → rewrite.

Senior-engineer test: "Would they say this is overcomplicated?" If yes, simplify.

## 3. Surgical changes

Touch only what you must. Clean up only your own mess.

- Don't improve adjacent code, comments, formatting.
- Don't refactor things that aren't broken.
- Match existing style.
- Unrelated dead code → mention, don't delete.
- Imports/vars *your* changes orphaned → remove. Pre-existing dead code → leave unless asked.

Test: every changed line traces directly to user's request.

## 4. Goal-driven execution

Define success criteria. Loop until verified.

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Tests pass before and after"

Multi-step → state brief plan with per-step verification.

Strong criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
