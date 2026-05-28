"""Ingestion CLI.

Usage:
    uv run python -m src.ingestion.cli -i data/a.pdf data/b.pdf
    uv run python -m src.ingestion.cli -b data/
"""

import argparse
import sys
from pathlib import Path

from loguru import logger

from src.core.config import settings
from src.ingestion.docling_parser import DoclingParser
from src.ingestion.indexer import QdrantIndexer
from src.ingestion.service import IngestionService
from src.llm import get_llm_provider

_LOG_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <7}</level> | "
    "<cyan>{name}</cyan> | "
    "{message}"
)


def _configure_logging(verbose: bool) -> None:
    """INFO by default (step-level progress). --verbose drops to DEBUG."""
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if verbose else "INFO",
        format=_LOG_FORMAT,
    )


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
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip LLM enrichment (table/figure/equation descriptions)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logs (per-chunk, per-step detail)",
    )
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if not args.input and not args.batch_dir:
        parser.error("Provide -i <files> or -b <directory>")

    pdf_paths = _collect_pdfs(args)
    if not pdf_paths:
        logger.error("No valid PDF files to process")
        sys.exit(1)

    doc_parser = DoclingParser(settings.docling)
    llm = None if args.no_enrich else get_llm_provider()
    service = IngestionService(
        parser=doc_parser,
        grobid_cfg=settings.grobid,
        chunking_cfg=settings.chunking,
        llm=llm,
    )
    indexer = QdrantIndexer(settings.qdrant)

    total_chunks = 0
    total_refs = 0
    processed = 0
    for i, path in enumerate(pdf_paths, 1):
        logger.info("[{}/{}] === START {} ===", i, len(pdf_paths), path.name)
        try:
            doc, chunks = service.process_pdf(path)
            if chunks:
                logger.info(
                    "[{}/{}] Indexing {} chunks", i, len(pdf_paths), len(chunks)
                )
                indexer.index(chunks)
            total_chunks += len(chunks)
            total_refs += len(doc.references)
            processed += 1
            logger.info(
                "[{}/{}] === DONE {} ({} chunks, {} refs) ===",
                i,
                len(pdf_paths),
                path.name,
                len(chunks),
                len(doc.references),
            )
        except Exception:
            logger.exception(
                "[{}/{}] FAILED {}, skipping", i, len(pdf_paths), path.name
            )

    logger.info(
        "Done: {} papers, {} chunks, {} references",
        processed,
        total_chunks,
        total_refs,
    )


if __name__ == "__main__":
    main()
