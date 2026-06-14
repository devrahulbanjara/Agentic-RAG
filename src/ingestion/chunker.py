from src.core.config import ChunkingSettings
from src.ingestion.chunker_helpers import (
    is_noise,
    merge_short_paragraphs,
    table_to_markdown,
)
from src.ingestion.schemas import Chunk, ParsedDocument, Section


def make_header(arxiv_id: str, section_label: str, label: str | None = None) -> str:
    """Build the header line that every chunk starts with.

    [Paper: 1706.03762 | Section: 3 Model Architecture > 3.2 Attention | Table: ...]
    The trailing ` | label` part is added only for table/figure/equation chunks.
    """
    tag = f" | {label}" if label else ""
    return f"[Paper: {arxiv_id} | Section: {section_label}{tag}]"


def chunk_document(document: ParsedDocument, config: ChunkingSettings) -> list[Chunk]:
    """Turn a parsed document into a list of chunks for embedding and storage.

    Goes through the document's section tree. For each section, handles every
    element in reading order:

    - paragraph: collected into a list. Consecutive short paragraphs get
      merged if their combined length <= config.merge_max_chars. When a
      non-paragraph element appears or the section ends, all collected
      paragraphs are merged and saved as chunks before moving on.
    - table: rendered as markdown with caption. Skipped if fewer than 2 rows.
    - figure: uses the caption text. Skipped if no caption or caption too short.
    - equation: uses the LaTeX string. Skipped if shorter than 5 characters.

    Every chunk starts with the paper ID and full section path, like:
    [Paper: 1706.03762 | Section: 3 Model Architecture > 3.2 Attention]

    Args:
        document: The parsed document (from Docling + GROBID).
        config: Chunking config with min_chars, merge_max_chars,
                skip_sections, etc.

    Returns:
        List of Chunk objects, each with text, arxiv_id, chunk_type, and
        section_path fields.
    """
    chunks: list[Chunk] = []

    def make_paragraph_chunk(
        text: str, arxiv_id: str, section_path: list[str], section_label: str
    ) -> Chunk:
        """Build a single paragraph Chunk with the standard header.

        Args:
            text: The paragraph text (may be multiple merged paragraphs).
            arxiv_id: The paper's arXiv ID, e.g. "1706.03762".
            section_path: List of section headings, e.g. ["3 Model Architecture", "3.2 Attention"].
            section_label: The section path joined with " > " for the header.

        Returns:
            A Chunk object with chunk_type="paragraph".
        """
        return Chunk(
            text=f"{make_header(arxiv_id, section_label)}\n{text}",
            arxiv_id=arxiv_id,
            chunk_type="paragraph",
            section_path=section_path,
        )

    def save_collected_paragraphs(
        paragraphs: list[str],
        arxiv_id: str,
        section_path: list[str],
        section_label: str,
    ) -> None:
        """Merge the collected paragraphs into chunks, then empty the list.

        Called when:
        1. We hit a table, figure, or equation — save all collected paragraphs
           before we deal with that element.
        2. We reach the end of a section — save whatever paragraphs are left.

        Does nothing if paragraphs is empty.

        Example — a section has: [para A, para B, TABLE, para C, para D]

            para A (100 chars) → collect
            para B (100 chars) → collect
            TABLE appears      → save_collected_paragraphs([A, B])
                                  merges A+B into one chunk, empties the list
                               → then handle TABLE as its own chunk
            para C (100 chars) → collect
            para D (100 chars) → collect
            section ends       → save_collected_paragraphs([C, D])
                                  merges C+D into one chunk

        Without this, A+B+C+D would all merge together, ignoring the table
        between B and C. The table breaks the flow — paragraphs before and
        after it are about different things, so they should not merge.

        Args:
            paragraphs: Paragraph text strings collected so far in this section.
            arxiv_id: The paper's arXiv ID.
            section_path: List of section headings for this section.
            section_label: The section path joined with " > " for the header.
        """
        for merged_text in merge_short_paragraphs(paragraphs, config.merge_max_chars):
            chunks.append(
                make_paragraph_chunk(merged_text, arxiv_id, section_path, section_label)
            )
        paragraphs.clear()

    def process_sections(sections: list[Section], parent_path: list[str]) -> None:
        for section in sections:
            heading = section.heading
            if heading in config.skip_sections:
                continue
            section_path = [*parent_path, heading]
            section_label = " > ".join(section_path)

            paragraphs: list[str] = []
            for item in section.content:
                if item.element_type == "paragraph":
                    text = (item.text or "").strip()
                    if is_noise(text, config.min_chars):
                        continue
                    paragraphs.append(text)

                elif item.element_type == "table":
                    save_collected_paragraphs(
                        paragraphs, document.arxiv_id, section_path, section_label
                    )

                    rows = item.rows
                    if not rows or len(rows) < 2:
                        continue
                    caption = item.caption or ""
                    markdown = table_to_markdown(rows)
                    label = f"Table: {caption}" if caption else "Table"
                    chunk_text = (
                        f"{make_header(document.arxiv_id, section_label, label)}\n"
                    )
                    if caption:
                        chunk_text += f"Caption: {caption}\n\n"
                    chunk_text += markdown
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            arxiv_id=document.arxiv_id,
                            chunk_type="table",
                            section_path=section_path,
                        )
                    )

                elif item.element_type == "figure":
                    save_collected_paragraphs(
                        paragraphs, document.arxiv_id, section_path, section_label
                    )

                    caption = item.caption or ""
                    if not caption or len(caption.strip()) < config.min_chars:
                        continue
                    label = f"Figure: {caption}" if caption else "Figure"
                    chunk_text = (
                        f"{make_header(document.arxiv_id, section_label, label)}\n"
                    )
                    chunk_text += f"Caption: {caption}"
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            arxiv_id=document.arxiv_id,
                            chunk_type="figure",
                            section_path=section_path,
                            image_path=item.image_path,
                        )
                    )

                elif item.element_type == "equation":
                    save_collected_paragraphs(
                        paragraphs, document.arxiv_id, section_path, section_label
                    )

                    latex = (item.latex or "").strip()
                    if not latex or len(latex) < 5:
                        continue
                    chunk_text = f"{make_header(document.arxiv_id, section_label, 'Equation')}\n{latex}"
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            arxiv_id=document.arxiv_id,
                            chunk_type="equation",
                            section_path=section_path,
                        )
                    )

            # Save any remaining paragraphs at end of section
            save_collected_paragraphs(
                paragraphs, document.arxiv_id, section_path, section_label
            )

            process_sections(section.children, section_path)

    process_sections(document.sections, [])
    return chunks
