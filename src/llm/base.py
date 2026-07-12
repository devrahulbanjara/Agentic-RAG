from abc import ABC, abstractmethod
from pathlib import Path

from src.llm.schemas import MetadataQuery, QueryClassification


class LLMError(Exception):
    """Base class for provider-agnostic LLM errors."""


class LLMRateLimitError(LLMError):
    """Raised when the provider returns a rate-limit/quota response (e.g. HTTP 429)."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class LLMDailyQuotaError(LLMError):
    """Raised when the daily request cap is reached and won't reset until midnight.

    Distinct from `LLMRateLimitError`: a per-minute limit clears in seconds and is
    worth waiting out, but the daily cap means every further call this run will
    fail, so callers should abort rather than retry chunk-by-chunk.
    """


class LLMProvider(ABC):
    """Adapter base for any LLM backend (Gemini, Groq, local).

    Implementations expose a uniform set of enrichment calls so callers
    (e.g. the ingestion enricher) never depend on a concrete provider.
    Swap providers by changing the factory configuration only.
    """

    @abstractmethod
    def describe_table(self, markdown: str, caption: str | None = None) -> str:
        """Return a 2-3 sentence description of a markdown table."""

    @abstractmethod
    def describe_figure(self, image_path: Path, caption: str | None = None) -> str:
        """Return a 2-3 sentence description of a figure image."""

    @abstractmethod
    def describe_equation(self, latex: str, context: str | None = None) -> str:
        """Return a 2-3 sentence description of a LaTeX equation."""

    @abstractmethod
    def extract_keywords(self, text: str) -> list[str]:
        """Return up to 15 retrieval keywords for the chunk."""

    @abstractmethod
    def generate_questions(self, text: str) -> list[str]:
        """Return 3 hypothetical questions the chunk answers."""

    @abstractmethod
    def classify_query(self, query: str) -> QueryClassification:
        """Classify a user turn into an intent and retrieval category for routing."""

    @abstractmethod
    def expand_query(self, query: str, count: int) -> list[str]:
        """Return `count` alternative phrasings of the query for RAG Fusion."""

    @abstractmethod
    def decompose_query(self, query: str) -> list[str]:
        """Return standalone sub-questions a comparative query decomposes into."""

    @abstractmethod
    def extract_metadata_query(self, query: str) -> MetadataQuery:
        """Extract metadata filters and the semantic part of the query."""

    @abstractmethod
    def generate_answer(self, query: str, context: str) -> str:
        """Answer the query using only the given context, citing each claim."""
