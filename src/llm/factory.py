from src.core.config import settings
from src.llm.base import LLMProvider
from src.llm.gemini import GeminiProvider


def get_llm_provider(model: str | None = None) -> LLMProvider:
    """Return the LLM provider configured by `settings.llm.provider`.

    Swap providers by changing `LLM_PROVIDER` in env. Add new branches here
    when implementing Groq, Ollama, etc. `model` overrides the provider's
    default model — used to run the router on a faster, cheaper model than
    enrichment.
    """
    provider = settings.llm.provider.lower()
    if provider == "gemini":
        return GeminiProvider(model=model)
    raise NotImplementedError(f"LLM provider '{provider}' is not implemented")
