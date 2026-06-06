# Production Ready Agentic RAG System

Production-grade RAG over arXiv papers. Two-stage pipeline: offline indexing, runtime inference. Evaluated continuously, stress-tested for failure modes.

## Architecture

<p align="center">
  <img src="docs/assets/architecture.png" alt="Production Grade RAG Architecture" width="1000">
</p>

## Process
### Ingestion
Either ingesting selected documents then:
```
uv run python -m src.ingestion.cli -i data/a.pdf data/b.pdf
```
For entire folder of documents
```
uv run python -m src.ingestion.cli -b data/
```

Running ingestion the first time will take a bit more time than subsequent runs even for the same data, as docling will download its model for the first time.
