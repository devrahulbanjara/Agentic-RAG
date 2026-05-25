"""Ingestion CLI.

Usage:
    uv run python -m src.ingestion.cli -i data/a.pdf data/b.pdf
    uv run python -m src.ingestion.cli -b data/
"""

import argparse
import sys
from pathlib import Path

from loguru import logger

from src.ingestion.config import IngestionSettings
from src.ingestion.docling_parser import DoclingParser
from src.ingestion.indexer import QdrantIndexer
from src.ingestion.service import IngestionService


def _collect_pdfs(args: argparse.Namespace) -> list[Path]:
    """Resolve PDF paths from -i (individual files) or -b (batch directory)."""
    paths: list[Path] = []

    if args.batch_dir:
        found = sorted(args.batch_dir.glob("*.pdf"))
        if not found:
            logger.error("No PDFs found in {}", args.batch_dir)
            sys.exit(1)
        paths.extend(found)

    if args.input:
        for p in args.input:
            if not p.exists():
                logger.warning("File not found, skipping: {}", p)
                continue
            paths.append(p)

    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Parse and chunk arXiv PDFs")
    parser.add_argument("-i", "--input", nargs="+", type=Path, help="PDF file(s)")
    parser.add_argument("-b", "--batch-dir", type=Path, help="Directory of PDFs")
    args = parser.parse_args(argv)

    if not args.input and not args.batch_dir:
        parser.error("Provide -i <files> or -b <directory>")

    pdf_paths = _collect_pdfs(args)
    if not pdf_paths:
        logger.error("No valid PDF files to process")
        sys.exit(1)

    settings = IngestionSettings()
    doc_parser = DoclingParser(settings)
    service = IngestionService(parser=doc_parser, settings=settings)

    all_chunks = []
    total_refs = 0
    processed = 0
    for i, path in enumerate(pdf_paths, 1):
        logger.info("[{}/{}] Processing {}", i, len(pdf_paths), path.name)
        try:
            doc, chunks = service.process_pdf(path)
            all_chunks.extend(chunks)
            total_refs += len(doc.references)
            processed += 1
        except Exception:
            logger.exception("Failed to process {}, skipping", path.name)

    if all_chunks:
        indexer = QdrantIndexer(settings)
        indexer.index(all_chunks)

    logger.info(
        "Done: {} papers, {} chunks, {} references",
        processed,
        len(all_chunks),
        total_refs,
    )


if __name__ == "__main__":
    main()
