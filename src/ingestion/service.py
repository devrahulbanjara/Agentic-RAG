from pathlib import Path

from loguru import logger

from src.ingestion.chunker import chunk_document
from src.ingestion.config import IngestionSettings
from src.ingestion.docling_parser import DoclingParser
from src.ingestion.grobid_client import extract_references
from src.ingestion.schemas import Chunk, ParsedDocument


class IngestionService:
    """Orchestrates PDF parsing, reference extraction, and chunking."""

    def __init__(
        self,
        parser: DoclingParser,
        settings: IngestionSettings,
    ) -> None:
        self._parser = parser
        self._settings = settings

    def process_pdf(self, pdf_path: Path) -> tuple[ParsedDocument, list[Chunk]]:
        """Parse one PDF, extract references, chunk. Returns structured data."""
        doc = self._parser.parse(pdf_path)

        s = self._settings
        if s.grobid_enabled:
            doc.references = extract_references(
                s.grobid_url, s.grobid_timeout, pdf_path
            )
            logger.info(
                "{}: {} references from GROBID", doc.arxiv_id, len(doc.references)
            )

        chunks = chunk_document(doc, self._settings)
        logger.info(
            "{}: {} sections, {} chunks",
            doc.arxiv_id,
            len(doc.sections),
            len(chunks),
        )
        return doc, chunks
