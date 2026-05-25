import re

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


def _make_element(item, doc) -> DocumentElement | None:
    """Convert a single Docling item into a DocumentElement."""
    if isinstance(item, TableItem):
        df = item.export_to_dataframe(doc=doc)
        rows = [[str(c) for c in df.columns]] + [
            [str(v) for v in row] for row in df.values
        ]
        return DocumentElement(
            element_type="table",
            caption=item.caption_text(doc=doc) or None,
            rows=rows,
        )

    if isinstance(item, PictureItem):
        return DocumentElement(
            element_type="figure",
            caption=item.caption_text(doc=doc) or None,
            has_image=item.image is not None,
        )

    if isinstance(item, TextItem):
        text = item.text
        if text.strip().startswith("$") or "\\frac" in text or "\\sum" in text:
            return DocumentElement(element_type="equation", latex=text)
        return DocumentElement(element_type="paragraph", text=text)

    return None


def build_tree(doc) -> tuple[list[Section], list[DocumentElement]]:
    """Build structured section tree from a Docling document.

    Returns (sections, abstract) where abstract holds elements that appear
    before the first section header.
    """
    for item, _ in doc.iterate_items():
        if isinstance(item, SectionHeaderItem):
            item.level = infer_heading_level(item.text)

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

        element = _make_element(item, doc)
        if element is None:
            continue

        target = section_stack[-1][1].content if section_stack else abstract
        target.append(element)

    return sections, abstract
