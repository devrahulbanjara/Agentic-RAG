from pathlib import Path

from loguru import logger

from src.core.config import ChunkingSettings, GrobidSettings
from src.ingestion.chunker import chunk_document
from src.ingestion.docling_parser import DoclingParser
from src.ingestion.enricher import enrich_chunks, enrich_metadata
from src.ingestion.grobid_client import extract_references
from src.ingestion.schemas import Chunk, ParsedDocument
from src.llm.base import LLMProvider


class IngestionService:
    """Orchestrates PDF parsing, reference extraction, chunking, enrichment."""

    def __init__(
        self,
        parser: DoclingParser,
        grobid_config: GrobidSettings,
        chunking_config: ChunkingSettings,
        llm: LLMProvider | None = None,
    ) -> None:
        self._parser = parser
        self._grobid = grobid_config
        self._chunking = chunking_config
        self._llm = llm

    def process_pdf(self, pdf_path: Path) -> tuple[ParsedDocument, list[Chunk]]:
        """Parse one PDF, extract references, chunk, optionally enrich."""
        logger.info("Step 1/4: Parsing PDF with Docling")
        document = self._parser.parse(pdf_path)
        logger.debug(
            "{}: parsed {} top-level sections",
            document.arxiv_id,
            len(document.sections),
        )

        if self._grobid.enabled:
            logger.info("Step 2/4: Extracting references via GROBID")
            document.references = extract_references(
                self._grobid.url, self._grobid.timeout, pdf_path
            )
            logger.info(
                "{}: {} references", document.arxiv_id, len(document.references)
            )
        else:
            logger.debug("GROBID disabled, skipping reference extraction")

        logger.info("Step 3/4: Chunking document")
        chunks = chunk_document(document, self._chunking)
        chunk_type_counts = _count_chunk_types(chunks)
        logger.info(
            "{}: {} chunks ({} paragraph, {} table, {} figure, {} equation)",
            document.arxiv_id,
            len(chunks),
            chunk_type_counts["paragraph"],
            chunk_type_counts["table"],
            chunk_type_counts["figure"],
            chunk_type_counts["equation"],
        )

        if self._llm is not None:
            non_paragraph_count = len(chunks) - chunk_type_counts["paragraph"]
            logger.info(
                "Step 4/5: Enriching {} non-paragraph chunks with descriptions",
                non_paragraph_count,
            )
            chunks = enrich_chunks(chunks, self._llm)
            logger.info(
                "Step 5/5: Generating questions + keywords for all {} chunks",
                len(chunks),
            )
            chunks = enrich_metadata(chunks, self._llm)
        else:
            logger.info("Step 4/5: Enrichment skipped (--no-enrich)")

        return document, chunks


def _count_chunk_types(chunks: list[Chunk]) -> dict[str, int]:
    counts = {"paragraph": 0, "table": 0, "figure": 0, "equation": 0}
    for chunk in chunks:
        counts[chunk.chunk_type] = counts.get(chunk.chunk_type, 0) + 1
    return counts
