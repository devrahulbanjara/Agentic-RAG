from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from loguru import logger

from src.core.config import DoclingSettings
from src.ingestion.arxiv_metadata import (
    build_fallback_metadata,
    fetch_paper_metadata,
    looks_like_arxiv_id,
)
from src.ingestion.docling_parser_helpers import build_tree
from src.ingestion.schemas import ParsedDocument


class DoclingParser:
    def __init__(self, config: DoclingSettings) -> None:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = config.do_ocr
        pipeline_options.do_formula_enrichment = config.do_formula_enrichment
        pipeline_options.generate_page_images = False
        pipeline_options.generate_picture_images = config.generate_picture_images
        pipeline_options.images_scale = config.images_scale
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=config.num_threads,
            device=AcceleratorDevice.CPU,
        )
        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        self._figure_output_dir = Path(config.figure_output_dir)

    def parse(self, pdf_path: Path) -> ParsedDocument:
        """Parse a single PDF into a structured document."""
        raw_arxiv_id = pdf_path.stem
        metadata = None
        if looks_like_arxiv_id(raw_arxiv_id):
            try:
                metadata = fetch_paper_metadata(raw_arxiv_id)
                logger.debug(
                    "Loaded arXiv metadata {} {}",
                    metadata.arxiv_id,
                    metadata.version,
                )
            except Exception as error:
                logger.warning(
                    "Could not load arXiv metadata for {}: {}. Continuing with filename-derived metadata.",
                    raw_arxiv_id,
                    error,
                )
        else:
            logger.debug(
                "Skipping arXiv metadata lookup for non-arXiv filename {}",
                raw_arxiv_id,
            )

        arxiv_id = metadata.arxiv_id if metadata else raw_arxiv_id
        logger.debug("Parsing {} with Docling", arxiv_id)

        logger.debug("  Docling: converting PDF (this is the slowest stage)")
        result = self._converter.convert(str(pdf_path))
        metadata = metadata or build_fallback_metadata(
            raw_arxiv_id, result.document.name
        )
        logger.debug("  Docling: conversion done, building section tree")
        sections, _ = build_tree(
            result.document,
            figure_dir=self._figure_output_dir,
            arxiv_id=arxiv_id,
        )
        logger.debug("  Docling: section tree built ({} top-level)", len(sections))

        return ParsedDocument(
            arxiv_id=arxiv_id,
            title=metadata.title or result.document.name,
            metadata=metadata,
            sections=sections,
            references=[],
        )
