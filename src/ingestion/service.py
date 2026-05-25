from pathlib import Path

from loguru import logger

from src.ingestion.chunker import chunk_document
from src.ingestion.config import IngestionSettings
from src.ingestion.docling_parser import DoclingParser
from src.ingestion.grobid_client import GrobidClient
from src.ingestion.schemas import Chunk, ParsedDocument


class IngestionService:
    """Orchestrates PDF parsing, reference extraction, and chunking."""

    def __init__(
        self,
        parser: DoclingParser,
        grobid: GrobidClient | None,
        settings: IngestionSettings,
    ) -> None:
        self._parser = parser
        self._grobid = grobid
        self._settings = settings

    def process_pdf(self, pdf_path: Path) -> tuple[ParsedDocument, list[Chunk]]:
        """Parse one PDF, extract references, chunk. Returns structured data."""
        doc = self._parser.parse(pdf_path)

        if self._grobid:
            doc.references = self._grobid.extract_references(pdf_path)
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

    def process_batch(
        self, pdf_paths: list[Path]
    ) -> list[tuple[ParsedDocument, list[Chunk]]]:
        """Process multiple PDFs. Skips failures, logs errors."""
        results: list[tuple[ParsedDocument, list[Chunk]]] = []
        for i, path in enumerate(pdf_paths, 1):
            logger.info("[{}/{}] Processing {}", i, len(pdf_paths), path.name)
            try:
                results.append(self.process_pdf(path))
            except Exception:
                logger.exception("Failed to process {}, skipping", path.name)
        return results
