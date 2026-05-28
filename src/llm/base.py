from abc import ABC, abstractmethod
from pathlib import Path


class LLMError(Exception):
    """Base class for provider-agnostic LLM errors."""


class LLMRateLimitError(LLMError):
    """Raised when the provider returns a rate-limit/quota response (e.g. HTTP 429)."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


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
