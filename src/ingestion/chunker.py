import re

from src.ingestion.config import IngestionSettings
from src.ingestion.schemas import Chunk, ParsedDocument, Section


def is_noise(text: str, min_chars: int) -> bool:
    """Filter out Docling artifacts and non-content text."""
    t = text.strip()
    if len(t) < min_chars:
        return True
    if re.match(r"^DRAFT\b", t):
        return True
    if re.match(r"^Keywords?:", t):
        return True
    if re.match(r"^[\w.\-]+@[\w.\-]+\.\w+$", t):
        return True
    return False


def chunk_document(doc: ParsedDocument, settings: IngestionSettings) -> list[Chunk]:
    """Create paragraph chunks with section path prefix from parsed document."""
    chunks: list[Chunk] = []

    def _add_paragraph_chunks(elements: list, path: list[str], label: str) -> None:
        for item in elements:
            if item.element_type != "paragraph":
                continue
            text = (item.text or "").strip()
            if is_noise(text, settings.min_chunk_chars):
                continue

            prefixed = f"[Paper: {doc.arxiv_id} | Section: {label}]\n{text}"
            chunks.append(
                Chunk(
                    text=prefixed,
                    arxiv_id=doc.arxiv_id,
                    chunk_type="paragraph",
                    section_path=path,
                )
            )

    def walk(sections: list[Section], path: list[str]) -> None:
        for section in sections:
            heading = section.heading
            if heading in settings.skip_sections:
                continue
            current_path = [*path, heading]
            section_str = " > ".join(current_path)
            _add_paragraph_chunks(section.content, current_path, section_str)
            walk(section.children, current_path)

    walk(doc.sections, [])
    return chunks
