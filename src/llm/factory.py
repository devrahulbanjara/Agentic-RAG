from src.core.config import settings
from src.llm.base import LLMProvider
from src.llm.gemini import GeminiProvider


def get_llm_provider() -> LLMProvider:
    """Return the LLM provider configured by `settings.llm.provider`.

    Swap providers by changing `LLM_PROVIDER` in env. Add new branches here
    when implementing Groq, Ollama, etc.
    """
    provider = settings.llm.provider.lower()
    if provider == "gemini":
        return GeminiProvider()
    raise NotImplementedError(f"LLM provider '{provider}' is not implemented")
