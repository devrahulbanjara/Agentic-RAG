from pathlib import Path

from loguru import logger

from src.core.config import ChunkingSettings, GrobidSettings
from src.ingestion.chunker import chunk_document
from src.ingestion.docling_parser import DoclingParser
from src.ingestion.enricher import enrich_chunks
from src.ingestion.grobid_client import extract_references
from src.ingestion.schemas import Chunk, ParsedDocument
from src.llm.base import LLMProvider


class IngestionService:
    """Orchestrates PDF parsing, reference extraction, chunking, enrichment."""

    def __init__(
        self,
        parser: DoclingParser,
        grobid_cfg: GrobidSettings,
        chunking_cfg: ChunkingSettings,
        llm: LLMProvider | None = None,
    ) -> None:
        self._parser = parser
        self._grobid = grobid_cfg
        self._chunking = chunking_cfg
        self._llm = llm

    def process_pdf(self, pdf_path: Path) -> tuple[ParsedDocument, list[Chunk]]:
        """Parse one PDF, extract references, chunk, optionally enrich."""
        logger.info("Step 1/4: Parsing PDF with Docling")
        doc = self._parser.parse(pdf_path)
        logger.debug(
            "{}: parsed {} top-level sections", doc.arxiv_id, len(doc.sections)
        )

        if self._grobid.enabled:
            logger.info("Step 2/4: Extracting references via GROBID")
            doc.references = extract_references(
                self._grobid.url, self._grobid.timeout, pdf_path
            )
            logger.info("{}: {} references", doc.arxiv_id, len(doc.references))
        else:
            logger.debug("GROBID disabled, skipping reference extraction")

        logger.info("Step 3/4: Chunking document")
        chunks = chunk_document(doc, self._chunking)
        type_counts = _count_chunk_types(chunks)
        logger.info(
            "{}: {} chunks ({} paragraph, {} table, {} figure, {} equation)",
            doc.arxiv_id,
            len(chunks),
            type_counts["paragraph"],
            type_counts["table"],
            type_counts["figure"],
            type_counts["equation"],
        )

        if self._llm is not None:
            non_para = len(chunks) - type_counts["paragraph"]
            logger.info("Step 4/4: Enriching {} non-paragraph chunks via LLM", non_para)
            chunks = enrich_chunks(chunks, self._llm)
        else:
            logger.info("Step 4/4: Enrichment skipped (--no-enrich)")

        return doc, chunks


def _count_chunk_types(chunks: list[Chunk]) -> dict[str, int]:
    counts = {"paragraph": 0, "table": 0, "figure": 0, "equation": 0}
    for c in chunks:
        counts[c.chunk_type] = counts.get(c.chunk_type, 0) + 1
    return counts
