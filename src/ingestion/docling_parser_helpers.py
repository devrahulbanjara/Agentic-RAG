import re
from pathlib import Path
from typing import Callable

from docling_core.types.doc import (
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
)

from src.ingestion.schemas import DocumentElement, Section


def infer_heading_level(text: str) -> int:
    """Infer heading level from numbering pattern. Covers arXiv LaTeX conventions."""
    t = text.strip()
    if re.match(r"^\d+\.\d+\.\d+", t):
        return 3
    if re.match(r"^\d+\.\d+", t):
        return 2
    if re.match(r"^[A-Z]\.\d+", t):
        return 2
    if re.match(r"^\d+\s", t):
        return 1
    return 1


def _make_element(
    item,
    doc,
    save_figure: Callable[[PictureItem], str | None] | None,
) -> DocumentElement | None:
    """Convert a single Docling item into a DocumentElement.

    If `save_figure` is provided and the item is a PictureItem with an
    image, it is invoked to persist the image to disk; the returned path
    is attached to the element.
    """
    if isinstance(item, TableItem):
        dataframe = item.export_to_dataframe(doc=doc)
        rows = [[str(column) for column in dataframe.columns]] + [
            [str(value) for value in row] for row in dataframe.values
        ]
        return DocumentElement(
            element_type="table",
            caption=item.caption_text(doc=doc) or None,
            rows=rows,
        )

    if isinstance(item, PictureItem):
        image_path = save_figure(item) if save_figure else None
        return DocumentElement(
            element_type="figure",
            caption=item.caption_text(doc=doc) or None,
            has_image=item.image is not None,
            image_path=image_path,
        )

    if isinstance(item, TextItem):
        text = item.text
        if text.strip().startswith("$") or "\\frac" in text or "\\sum" in text:
            return DocumentElement(element_type="equation", latex=text)
        return DocumentElement(element_type="paragraph", text=text)

    return None


def _make_figure_saver(
    figure_dir: Path, arxiv_id: str
) -> Callable[[PictureItem], str | None]:
    """Return a callable that saves PictureItem images under figure_dir/arxiv_id."""
    counter = {"idx": 0}

    def save(item: PictureItem) -> str | None:
        if item.image is None:
            return None
        output_dir = figure_dir / arxiv_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"fig_{counter['idx']}.png"
        item.image.pil_image.save(str(output_path))
        counter["idx"] += 1
        return str(output_path)

    return save


def build_tree(
    doc,
    figure_dir: Path | None = None,
    arxiv_id: str | None = None,
) -> tuple[list[Section], list[DocumentElement]]:
    """Build structured section tree from a Docling document.

    Returns (sections, abstract) where abstract holds elements that appear
    before the first section header. When `figure_dir` and `arxiv_id` are
    set, figure images are saved to disk and their paths attached to the
    corresponding figure elements.
    """
    for item, _ in doc.iterate_items():
        if isinstance(item, SectionHeaderItem):
            item.level = infer_heading_level(item.text)

    save_figure = (
        _make_figure_saver(figure_dir, arxiv_id) if figure_dir and arxiv_id else None
    )

    sections: list[Section] = []
    abstract: list[DocumentElement] = []
    section_stack: list[tuple[int, Section]] = []

    for item, _ in doc.iterate_items():
        if isinstance(item, SectionHeaderItem):
            section = Section(
                heading=item.text,
                level=item.level,
                content=[],
                children=[],
            )
            while section_stack and section_stack[-1][0] >= item.level:
                section_stack.pop()
            if section_stack:
                section_stack[-1][1].children.append(section)
            else:
                sections.append(section)
            section_stack.append((item.level, section))
            continue

        element = _make_element(item, doc, save_figure)
        if element is None:
            continue

        destination = section_stack[-1][1].content if section_stack else abstract
        destination.append(element)

    return sections, abstract
