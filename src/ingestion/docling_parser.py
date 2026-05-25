from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import PictureItem
from loguru import logger

from src.ingestion.config import IngestionSettings
from src.ingestion.docling_parser_helpers import build_tree
from src.ingestion.schemas import ParsedDocument


class DoclingParser:
    def __init__(self, settings: IngestionSettings) -> None:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = settings.do_ocr
        pipeline_options.do_formula_enrichment = settings.do_formula_enrichment
        pipeline_options.generate_page_images = False
        pipeline_options.generate_picture_images = settings.generate_picture_images
        pipeline_options.images_scale = settings.images_scale
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=settings.num_threads,
            device=AcceleratorDevice.CPU,
        )
        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        self._figure_output_dir = Path(settings.figure_output_dir)

    def parse(self, pdf_path: Path) -> ParsedDocument:
        """Parse a single PDF into a structured document."""
        arxiv_id = pdf_path.stem
        logger.info("Parsing {} with Docling", arxiv_id)

        result = self._converter.convert(str(pdf_path))
        sections, preamble = build_tree(result.document)
        self._save_figures(result.document, arxiv_id)

        return ParsedDocument(
            arxiv_id=arxiv_id,
            title=result.document.name,
            sections=sections,
            preamble=preamble,
            references=[],
        )

    def _save_figures(self, doc, arxiv_id: str) -> None:
        """Save extracted figure images to disk."""
        fig_idx = 0
        for item, _ in doc.iterate_items():
            if isinstance(item, PictureItem) and item.image is not None:
                fig_dir = self._figure_output_dir / arxiv_id
                fig_dir.mkdir(parents=True, exist_ok=True)
                out_path = fig_dir / f"fig_{fig_idx}.png"
                item.image.pil_image.save(str(out_path))
                fig_idx += 1
        if fig_idx:
            logger.info("Saved {} figures for {}", fig_idx, arxiv_id)
