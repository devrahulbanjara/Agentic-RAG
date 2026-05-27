from src.ingestion.chunker_helpers import (
    is_noise,
    merge_short_paragraphs,
    table_to_markdown,
)
from src.ingestion.config import IngestionSettings
from src.ingestion.schemas import Chunk, ParsedDocument, Section


def chunk_document(doc: ParsedDocument, settings: IngestionSettings) -> list[Chunk]:
    """Turn a parsed document into a list of chunks for embedding and storage.

    Walks the document's section tree. For each section, processes every
    element in reading order:

    - paragraph: collected into a list. Consecutive short paragraphs get
      merged if their combined length <= settings.merge_max_chars. When a
      non-paragraph element appears or the section ends, all collected
      paragraphs are merged and saved as chunks before moving on.
    - table: rendered as markdown with caption. Skipped if fewer than 2 rows.
    - figure: uses the caption text. Skipped if no caption or caption too short.
    - equation: uses the LaTeX string. Skipped if shorter than 5 characters.

    Every chunk is prefixed with the paper ID and full section path, like:
    [Paper: 1706.03762 | Section: 3 Model Architecture > 3.2 Attention]

    Args:
        doc: The parsed document (from Docling + GROBID).
        settings: Ingestion config with min_chunk_chars, merge_max_chars,
                  skip_sections, etc.

    Returns:
        List of Chunk objects, each with text, arxiv_id, chunk_type, and
        section_path fields.
    """
    chunks: list[Chunk] = []

    def _make_paragraph_chunk(
        text: str, arxiv_id: str, section_path: list[str], section_str: str
    ) -> Chunk:
        """Build a single paragraph Chunk with the standard prefix.

        Args:
            text: The paragraph text (may be multiple merged paragraphs).
            arxiv_id: The paper's arXiv ID, e.g. "1706.03762".
            section_path: List of section headings, e.g. ["3 Model Architecture", "3.2 Attention"].
            section_str: The section path joined with " > " for the prefix.

        Returns:
            A Chunk object with chunk_type="paragraph".
        """
        return Chunk(
            text=f"[Paper: {arxiv_id} | Section: {section_str}]\n{text}",
            arxiv_id=arxiv_id,
            chunk_type="paragraph",
            section_path=section_path,
        )

    def _save_collected_paragraphs(
        para_texts: list[str], arxiv_id: str, section_path: list[str], section_str: str
    ) -> None:
        """Take the paragraphs we've been collecting, merge short ones, and save them as chunks.

        Called when:
        1. We hit a table, figure, or equation — save all collected paragraphs
           before we deal with that element.
        2. We reach the end of a section — save whatever paragraphs are left.

        Does nothing if para_texts is empty.

        Example — a section has: [para A, para B, TABLE, para C, para D]

            para A (100 chars) → collect
            para B (100 chars) → collect
            TABLE appears      → _save_collected_paragraphs([A, B])
                                  merges A+B into one chunk, clears the list
                               → then process TABLE as its own chunk
            para C (100 chars) → collect
            para D (100 chars) → collect
            section ends       → _save_collected_paragraphs([C, D])
                                  merges C+D into one chunk

        Without this, A+B+C+D would all merge together, ignoring the table
        between B and C. The table breaks the flow — paragraphs before and
        after it are about different things, so they should not merge.

        Args:
            para_texts: Paragraph text strings collected so far in this section.
            arxiv_id: The paper's arXiv ID.
            section_path: List of section headings for this section.
            section_str: The section path joined with " > " for the prefix.
        """
        for merged_text in merge_short_paragraphs(para_texts, settings.merge_max_chars):
            chunks.append(
                _make_paragraph_chunk(merged_text, arxiv_id, section_path, section_str)
            )

    def walk(sections: list[Section], path: list[str]) -> None:
        for section in sections:
            heading = section.heading
            if heading in settings.skip_sections:
                continue
            current_path = [*path, heading]
            section_str = " > ".join(current_path)

            para_texts: list[str] = []
            for item in section.content:
                if item.element_type == "paragraph":
                    text = (item.text or "").strip()
                    if is_noise(text, settings.min_chunk_chars):
                        continue
                    para_texts.append(text)

                elif item.element_type == "table":
                    _save_collected_paragraphs(
                        para_texts, doc.arxiv_id, current_path, section_str
                    )
                    para_texts = []

                    rows = item.rows
                    if not rows or len(rows) < 2:
                        continue
                    caption = item.caption or ""
                    md = table_to_markdown(rows)
                    label = f"Table: {caption}" if caption else "Table"
                    prefixed = (
                        f"[Paper: {doc.arxiv_id} | Section: {section_str} | {label}]\n"
                    )
                    if caption:
                        prefixed += f"Caption: {caption}\n\n"
                    prefixed += md
                    chunks.append(
                        Chunk(
                            text=prefixed,
                            arxiv_id=doc.arxiv_id,
                            chunk_type="table",
                            section_path=current_path,
                        )
                    )

                elif item.element_type == "figure":
                    _save_collected_paragraphs(
                        para_texts, doc.arxiv_id, current_path, section_str
                    )
                    para_texts = []

                    caption = item.caption or ""
                    if not caption or len(caption.strip()) < settings.min_chunk_chars:
                        continue
                    label = f"Figure: {caption}" if caption else "Figure"
                    prefixed = (
                        f"[Paper: {doc.arxiv_id} | Section: {section_str} | {label}]\n"
                    )
                    prefixed += f"Caption: {caption}"
                    chunks.append(
                        Chunk(
                            text=prefixed,
                            arxiv_id=doc.arxiv_id,
                            chunk_type="figure",
                            section_path=current_path,
                        )
                    )

                elif item.element_type == "equation":
                    _save_collected_paragraphs(
                        para_texts, doc.arxiv_id, current_path, section_str
                    )
                    para_texts = []

                    latex = (item.latex or "").strip()
                    if not latex or len(latex) < 5:
                        continue
                    prefixed = f"[Paper: {doc.arxiv_id} | Section: {section_str} | Equation]\n{latex}"
                    chunks.append(
                        Chunk(
                            text=prefixed,
                            arxiv_id=doc.arxiv_id,
                            chunk_type="equation",
                            section_path=current_path,
                        )
                    )

            # Save any remaining paragraphs at end of section
            _save_collected_paragraphs(
                para_texts, doc.arxiv_id, current_path, section_str
            )

            walk(section.children, current_path)

    walk(doc.sections, [])
    return chunks
