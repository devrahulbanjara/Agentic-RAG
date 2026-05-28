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
from src.ingestion.docling_parser_helpers import build_tree
from src.ingestion.schemas import ParsedDocument


class DoclingParser:
    def __init__(self, cfg: DoclingSettings) -> None:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = cfg.do_ocr
        pipeline_options.do_formula_enrichment = cfg.do_formula_enrichment
        pipeline_options.generate_page_images = False
        pipeline_options.generate_picture_images = cfg.generate_picture_images
        pipeline_options.images_scale = cfg.images_scale
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=cfg.num_threads,
            device=AcceleratorDevice.CPU,
        )
        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        self._figure_output_dir = Path(cfg.figure_output_dir)

    def parse(self, pdf_path: Path) -> ParsedDocument:
        """Parse a single PDF into a structured document."""
        arxiv_id = pdf_path.stem
        logger.debug("Parsing {} with Docling", arxiv_id)

        logger.debug("  Docling: converting PDF (this is the slowest stage)")
        result = self._converter.convert(str(pdf_path))
        logger.debug("  Docling: conversion done, building section tree")
        sections, _ = build_tree(
            result.document,
            figure_dir=self._figure_output_dir,
            arxiv_id=arxiv_id,
        )
        logger.debug("  Docling: section tree built ({} top-level)", len(sections))

        return ParsedDocument(
            arxiv_id=arxiv_id,
            title=result.document.name,
            sections=sections,
            references=[],
        )
