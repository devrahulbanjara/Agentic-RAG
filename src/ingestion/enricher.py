from pathlib import Path

from loguru import logger

from src.ingestion.schemas import Chunk
from src.llm.base import LLMError, LLMProvider, LLMRateLimitError


def _extract_table_markdown(chunk_text: str) -> str:
    """Strip the [Paper:...] / Caption: header lines, return raw markdown."""
    lines = chunk_text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("[Paper:"):
            body_start = i + 1
        elif line.startswith("Caption:"):
            body_start = i + 1
        elif line.strip() == "":
            body_start = i + 1
        else:
            break
    return "\n".join(lines[body_start:]).strip()


def _extract_equation_latex(chunk_text: str) -> str:
    """Strip header line, return raw LaTeX."""
    lines = chunk_text.splitlines()
    if lines and lines[0].startswith("[Paper:"):
        return "\n".join(lines[1:]).strip()
    return chunk_text.strip()


def enrich_chunks(chunks: list[Chunk], llm: LLMProvider) -> list[Chunk]:
    """Attach LLM-generated descriptions to non-paragraph chunks.

    Paragraph chunks are left untouched. Tables, figures, and equations
    get a natural-language `description` populated. Figure descriptions
    require an image at `chunk.image_path`; figures without one fall back
    to caption-only description.
    """
    enriched: list[Chunk] = []
    counts = {
        "table": 0,
        "figure": 0,
        "equation": 0,
        "skipped": 0,
        "failed": 0,
        "rate_limited": 0,
    }
    non_para_total = sum(1 for c in chunks if c.chunk_type != "paragraph")
    seen = 0

    for chunk in chunks:
        if chunk.chunk_type == "paragraph":
            enriched.append(chunk)
            continue

        seen += 1
        logger.debug(
            "  [{}/{}] describing {} chunk ({})",
            seen,
            non_para_total,
            chunk.chunk_type,
            " > ".join(chunk.section_path) or "—",
        )

        try:
            if chunk.chunk_type == "table":
                markdown = _extract_table_markdown(chunk.text)
                caption = _find_caption(chunk.text)
                description = llm.describe_table(markdown, caption)
                counts["table"] += 1

            elif chunk.chunk_type == "figure":
                caption = _find_caption(chunk.text)
                if chunk.image_path and Path(chunk.image_path).exists():
                    description = llm.describe_figure(Path(chunk.image_path), caption)
                else:
                    description = caption or ""
                    counts["skipped"] += 1
                counts["figure"] += 1

            elif chunk.chunk_type == "equation":
                latex = _extract_equation_latex(chunk.text)
                description = llm.describe_equation(latex)
                counts["equation"] += 1

            else:
                description = None

            enriched.append(chunk.model_copy(update={"description": description}))
        except LLMRateLimitError as exc:
            counts["rate_limited"] += 1
            retry_hint = (
                f" (retry in ~{exc.retry_after_seconds:.0f}s)"
                if exc.retry_after_seconds
                else ""
            )
            logger.warning(
                "LLM rate-limited, could not enrich {} chunk{}",
                chunk.chunk_type,
                retry_hint,
            )
            enriched.append(chunk)
        except LLMError as exc:
            counts["failed"] += 1
            logger.warning(
                "LLM error, could not enrich {} chunk: {}", chunk.chunk_type, exc
            )
            enriched.append(chunk)
        except Exception:
            counts["failed"] += 1
            logger.exception(
                "Unexpected enrichment failure for {} chunk", chunk.chunk_type
            )
            enriched.append(chunk)

    logger.info(
        "Enrichment done: {} tables, {} figures, {} equations "
        "({} skipped no-image, {} rate-limited, {} failed)",
        counts["table"],
        counts["figure"],
        counts["equation"],
        counts["skipped"],
        counts["rate_limited"],
        counts["failed"],
    )
    return enriched


def _find_caption(chunk_text: str) -> str | None:
    """Pull the caption line out of a prefixed chunk."""
    for line in chunk_text.splitlines():
        if line.startswith("Caption:"):
            return line[len("Caption:") :].strip()
    return None
