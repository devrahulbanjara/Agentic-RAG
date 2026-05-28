# Todos

## Idempotent, State-Driven Ingestion Pipeline

When processing hundreds of scientific documents, network issues, parser crashes, and API timeouts are inevitable.

**Strategy:** Design ingestion pipeline as an idempotent, state-driven state machine. Use status transitions on database rows:

```
pending → parsed → structured → chunked → enriched → embedded
```

**Why:** If pipeline fails on paper 427 due to an LLM rate-limit during enrichment, system must resume exactly where it left off. Database status acts as a checkpoint. Re-running pipeline bypasses successfully processed papers, saving compute and API costs.
