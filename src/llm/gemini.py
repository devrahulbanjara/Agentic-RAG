import re
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from loguru import logger
from PIL import Image

from src.core.config import settings
from src.llm.base import LLMError, LLMProvider, LLMRateLimitError
from src.llm.prompts import PromptLibrary, get_prompts
from src.llm.rate_limiter import FreeTierRateLimiter
from src.llm.schemas import Description, HypotheticalQuestions, Keywords

_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")
# Rough fallback when count_tokens is unavailable; ~4 chars/token for English text.
_CHARS_PER_TOKEN = 4


def _parse_retry_delay(message: str) -> float | None:
    """Pull `retryDelay: '6s'` out of a Gemini 429 error message, if present."""
    match = _RETRY_DELAY_RE.search(message)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        model: str | None = None,
        prompts: PromptLibrary | None = None,
    ) -> None:
        self._client = genai.Client(api_key=settings.llm.gemini_api_key)
        self._model = model or settings.llm.gemini_model
        self._output_token_buffer = settings.llm.output_token_buffer
        self._limiter = FreeTierRateLimiter(
            max_rpm=settings.llm.max_rpm,
            max_tpm=settings.llm.max_tpm,
            max_rpd=settings.llm.max_rpd,
            state_path=Path(settings.llm.daily_quota_state_path),
        )
        self._prompts = prompts or get_prompts()

    def _estimate_tokens(self, contents) -> int:
        """Count input tokens up front so the limiter can budget before sending.

        count_tokens is free and handles multimodal contents (figure images), but
        a transient failure must never sink enrichment — fall back to a char-based
        guess, which the response's actual usage corrects afterward anyway.
        """
        try:
            counted = self._client.models.count_tokens(
                model=self._model, contents=contents
            )
            return counted.total_tokens
        except Exception:
            text_length = sum(len(part) for part in contents if isinstance(part, str))
            return text_length // _CHARS_PER_TOKEN

    def _generate(self, contents, schema):
        estimated_tokens = self._estimate_tokens(contents) + self._output_token_buffer
        self._limiter.acquire(estimated_tokens)
        logger.debug("    Gemini call ({}, schema={})", self._model, schema.__name__)
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                    system_instruction=self._prompts.system,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except genai_errors.ClientError as error:
            if getattr(error, "code", None) == 429:
                raise LLMRateLimitError(
                    "Gemini quota exceeded (HTTP 429)",
                    retry_after_seconds=_parse_retry_delay(str(error)),
                ) from error
            raise LLMError(f"Gemini client error: {error}") from error
        except genai_errors.APIError as error:
            raise LLMError(f"Gemini API error: {error}") from error

        usage = response.usage_metadata
        actual_tokens = usage.total_token_count if usage else None
        self._limiter.record(actual_tokens if actual_tokens else estimated_tokens)
        return response.parsed

    def describe_table(self, markdown: str, caption: str | None = None) -> str:
        prompt = self._prompts.render(
            "describe_table", markdown=markdown, caption=caption
        )
        result: Description = self._generate([prompt], Description)
        return result.description

    def describe_figure(self, image_path: Path, caption: str | None = None) -> str:
        prompt = self._prompts.render("describe_figure", caption=caption)
        with Image.open(image_path) as image:
            result: Description = self._generate([prompt, image], Description)
        return result.description

    def describe_equation(self, latex: str, context: str | None = None) -> str:
        prompt = self._prompts.render("describe_equation", latex=latex, context=context)
        result: Description = self._generate([prompt], Description)
        return result.description

    def extract_keywords(self, text: str) -> list[str]:
        prompt = self._prompts.render("extract_keywords", text=text)
        result: Keywords = self._generate([prompt], Keywords)
        return result.keywords

    def generate_questions(self, text: str) -> list[str]:
        prompt = self._prompts.render("generate_questions", text=text)
        result: HypotheticalQuestions = self._generate([prompt], HypotheticalQuestions)
        return result.questions
