from collections import defaultdict

from src.retrieval.schemas import RetrievedChunk


def assemble_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into one context block the generation LLM reads.

    Chunks are grouped under their paper so same-paper evidence stays adjacent,
    and each passage carries a source tag the model copies into its citations.
    """
    chunks_by_paper: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_paper[chunk.arxiv_id].append(chunk)

    papers = []
    for arxiv_id, paper_chunks in chunks_by_paper.items():
        passages = [f"{_source_tag(chunk)}\n{chunk.text}" for chunk in paper_chunks]
        papers.append(f"## Paper arxiv:{arxiv_id}\n\n" + "\n\n".join(passages))
    return "\n\n---\n\n".join(papers)


def _source_tag(chunk: RetrievedChunk) -> str:
    """The citation tag shown above a passage, e.g. [arxiv:1706.03762, Section 3.1].

    Falls back to the chunk type when a passage has no section path (some tables
    and figures sit outside the section tree).
    """
    location = (
        " > ".join(chunk.section_path) if chunk.section_path else chunk.chunk_type
    )
    return f"[arxiv:{chunk.arxiv_id}, {location}]"
