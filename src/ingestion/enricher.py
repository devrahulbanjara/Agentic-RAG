from pathlib import Path

from loguru import logger
from src.ingestion.schemas import Chunk
from src.llm.base import (
    LLMDailyQuotaError,
    LLMError,
    LLMProvider,
    LLMRateLimitError,
)


def _retry_hint(error: LLMRateLimitError) -> str:
    """Format the optional ` (retry in ~6s)` suffix from a rate-limit error."""
    if error.retry_after_seconds:
        return f" (retry in ~{error.retry_after_seconds:.0f}s)"
    return ""


def _extract_table_markdown(chunk_text: str) -> str:
    """Strip the [Paper:...] / Caption: header lines, return raw markdown."""
    lines = chunk_text.splitlines()
    body_start = 0
    for index, line in enumerate(lines):
        if (
            line.startswith("[Paper:")
            or line.startswith("Caption:")
            or line.strip() == ""
        ):
            body_start = index + 1
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
    non_paragraph_total = sum(1 for c in chunks if c.chunk_type != "paragraph")
    seen = 0

    for chunk in chunks:
        if chunk.chunk_type == "paragraph":
            enriched.append(chunk)
            continue

        seen += 1
        logger.debug(
            "  [{}/{}] describing {} chunk ({})",
            seen,
            non_paragraph_total,
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
        except LLMDailyQuotaError:
            # Daily cap is spent — every remaining chunk would fail, so abort
            # the whole run instead of logging the same failure hundreds of times.
            raise
        except LLMRateLimitError as error:
            counts["rate_limited"] += 1
            logger.warning(
                "LLM rate-limited, could not enrich {} chunk{}",
                chunk.chunk_type,
                _retry_hint(error),
            )
            enriched.append(chunk)
        except LLMError as error:
            counts["failed"] += 1
            logger.warning(
                "LLM error, could not enrich {} chunk: {}", chunk.chunk_type, error
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


def enrich_metadata(chunks: list[Chunk], llm: LLMProvider) -> list[Chunk]:
    """Attach hypothetical questions and keywords to every chunk.

    For non-paragraph chunks the LLM-generated description is used as input
    (natural language embeds better than raw markdown/LaTeX). Falls back to
    chunk text if no description exists.
    """
    enriched: list[Chunk] = []
    counts = {"questions": 0, "keywords": 0, "rate_limited": 0, "failed": 0}
    total = len(chunks)

    def call_llm(llm_function, text, name, action, default, chunk_type, position):
        """Call one LLM enrichment. On failure, log it, count it, and return default."""
        try:
            result = llm_function(text)
            counts[name] += 1
            return result
        except LLMDailyQuotaError:
            raise
        except LLMRateLimitError as error:
            counts["rate_limited"] += 1
            logger.warning(
                "  [{}/{}] Rate-limited on {}{}",
                position,
                total,
                name,
                _retry_hint(error),
            )
        except Exception:
            counts["failed"] += 1
            logger.warning(
                "  [{}/{}] Failed to {} for {} chunk",
                position,
                total,
                action,
                chunk_type,
            )
        return default

    for position, chunk in enumerate(chunks, 1):
        source_text = (
            chunk.description
            if (chunk.chunk_type != "paragraph" and chunk.description)
            else chunk.text
        )

        questions = call_llm(
            llm.generate_questions,
            source_text,
            "questions",
            "generate questions",
            chunk.hypothetical_questions,
            chunk.chunk_type,
            position,
        )
        keywords = call_llm(
            llm.extract_keywords,
            source_text,
            "keywords",
            "extract keywords",
            chunk.keywords,
            chunk.chunk_type,
            position,
        )

        enriched.append(
            chunk.model_copy(
                update={"hypothetical_questions": questions, "keywords": keywords}
            )
        )
        logger.info(
            "  [{}/{}] {} chunk done: {} questions, {} keywords",
            position,
            total,
            chunk.chunk_type,
            len(questions),
            len(keywords),
        )

    logger.info(
        "Metadata enrichment done: {} question calls, {} keyword calls, "
        "{} rate-limited, {} failed",
        counts["questions"],
        counts["keywords"],
        counts["rate_limited"],
        counts["failed"],
    )
    return enriched
