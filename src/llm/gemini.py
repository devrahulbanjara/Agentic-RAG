import re
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from loguru import logger
from PIL import Image
from src.core.config import settings
from src.generation.messages import NO_EVIDENCE_REPLY
from src.llm.base import LLMError, LLMProvider, LLMRateLimitError
from src.llm.prompts import PromptLibrary, get_prompts
from src.llm.rate_limiter import FreeTierRateLimiter
from src.llm.schemas import (
    Description,
    GeneratedAnswer,
    HypotheticalQuestions,
    Keywords,
    MetadataQuery,
    QueryClassification,
    QueryVariations,
    SubQuestions,
)

_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")
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
            return counted.total_tokens or 0
        except Exception:
            text_length = sum(len(part) for part in contents if isinstance(part, str))
            return text_length // _CHARS_PER_TOKEN

    def _generate(self, contents, schema, *, system_instruction=None):
        estimated_tokens = self._estimate_tokens(contents) + self._output_token_buffer
        self._limiter.acquire(estimated_tokens)
        logger.debug(
            "llm call | model={} schema={} est_tokens={}",
            self._model,
            schema.__name__,
            estimated_tokens,
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                    system_instruction=system_instruction or self._prompts.system,
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
        logger.debug(
            "llm done | schema={} tokens={}",
            schema.__name__,
            actual_tokens or estimated_tokens,
        )
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

    def classify_query(self, query: str) -> QueryClassification:
        prompt = self._prompts.render("classify_query", query=query)
        system = self._prompts.render("classify_query_system")
        return self._generate([prompt], QueryClassification, system_instruction=system)

    def expand_query(self, query: str, count: int) -> list[str]:
        prompt = self._prompts.render("expand_query", query=query, count=count)
        result: QueryVariations = self._generate([prompt], QueryVariations)
        return result.variations

    def decompose_query(self, query: str) -> list[str]:
        prompt = self._prompts.render("decompose_query", query=query)
        result: SubQuestions = self._generate([prompt], SubQuestions)
        return result.sub_questions

    def extract_metadata_query(self, query: str) -> MetadataQuery:
        prompt = self._prompts.render("extract_metadata_query", query=query)
        return self._generate([prompt], MetadataQuery)

    def generate_answer(self, query: str, context: str) -> str:
        prompt = self._prompts.render("generate_answer", query=query, context=context)
        system = self._prompts.render(
            "generate_answer_system",
            no_evidence_reply=NO_EVIDENCE_REPLY,
        )
        result: GeneratedAnswer = self._generate(
            [prompt], GeneratedAnswer, system_instruction=system
        )
        return result.answer
