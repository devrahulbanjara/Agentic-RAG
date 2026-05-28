import re
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from loguru import logger
from PIL import Image

from src.core.config import settings
from src.llm.base import LLMError, LLMProvider, LLMRateLimitError
from src.llm.prompts import PromptLibrary, get_prompts
from src.llm.schemas import Description, HypotheticalQuestions, Keywords

_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")


def _parse_retry_delay(message: str) -> float | None:
    """Pull `retryDelay: '6s'` out of a Gemini 429 error message, if present."""
    m = _RETRY_DELAY_RE.search(message)
    if not m:
        return None
    try:
        return float(m.group(1))
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
        self._sleep_seconds = max(0.0, settings.llm.sleep_seconds)
        self._last_call_ts: float | None = None
        self._prompts = prompts or get_prompts()

    def _throttle(self) -> None:
        """Sleep just enough to keep at least `llm_sleep_seconds` between calls."""
        if self._sleep_seconds <= 0 or self._last_call_ts is None:
            return
        elapsed = time.monotonic() - self._last_call_ts
        remaining = self._sleep_seconds - elapsed
        if remaining > 0:
            logger.debug("    Throttling LLM: sleeping {:.1f}s", remaining)
            time.sleep(remaining)

    def _generate(self, contents, schema):
        self._throttle()
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
        except genai_errors.ClientError as exc:
            if getattr(exc, "code", None) == 429:
                raise LLMRateLimitError(
                    "Gemini quota exceeded (HTTP 429)",
                    retry_after_seconds=_parse_retry_delay(str(exc)),
                ) from exc
            raise LLMError(f"Gemini client error: {exc}") from exc
        except genai_errors.APIError as exc:
            raise LLMError(f"Gemini API error: {exc}") from exc
        finally:
            self._last_call_ts = time.monotonic()
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
