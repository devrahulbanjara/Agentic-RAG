# Python · FastAPI · LangChain · Pydantic — Deep Patterns

Extended reference for the `human-like-code` skill. Read this when the user's task involves any of these frameworks.

---

## FastAPI: Router Architecture

### Never Use a Bare `app` in Feature Code
`app = FastAPI()` belongs only in `main.py` / `app.py` at the entry point. Feature modules use `APIRouter`.

```python
# ❌ AI — global app instance in feature file
from fastapi import FastAPI
app = FastAPI()

@app.post("/generate")
async def generate(): ...


# ✅ Human — APIRouter, composed at entry point
from fastapi import APIRouter, Depends, status

router = APIRouter(
    prefix="/v1/agents",
    tags=["AI Agents"],
    responses={404: {"description": "Not found"}},
)

@router.post(
    "/generate",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Process user query via active LLM pipeline",
    description="Accepts a clean user prompt and returns the agent's generated response.",
)
async def handle_agent_generation(
    payload: AgentRequest,
    pipeline=Depends(get_agent_pipeline),
):
    ...
```

### Dependency Injection Patterns
```python
# src/apps/agents/dependencies.py
from functools import lru_cache
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.core.config import settings

@lru_cache(maxsize=1)
def _build_pipeline():
    """
    Singleton-per-process: expensive LLM client built once, reused.
    lru_cache is process-scoped — safe for stateless async functions.
    """
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
    )
    prompt = ChatPromptTemplate.from_template(
        "You are a helpful assistant. Answer clearly: {query}"
    )
    return prompt | llm | StrOutputParser()


def get_agent_pipeline():
    """FastAPI dependency — yields the cached pipeline instance."""
    return _build_pipeline()
```

### Lifespan Events (Startup / Shutdown)
```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.infrastructure.db import database
from src.apps.agents.router import router as agents_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: open connections, warm caches
    await database.connect()
    yield
    # Shutdown: clean up resources
    await database.disconnect()

app = FastAPI(title="My Service", version="1.0.0", lifespan=lifespan)
app.include_router(agents_router)
```

---

## Pydantic v2: Strict Schemas

### Field Constraints
```python
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Annotated

# Use Annotated for reusable constraint types
NonEmptyStr = Annotated[str, Field(min_length=1, max_length=255)]
UserIdStr = Annotated[str, Field(pattern=r"^usr_[a-zA-Z0-9]{16}$")]

class AgentRequest(BaseModel):
    model_config = {"str_strip_whitespace": True, "frozen": True}

    prompt: Annotated[str, Field(min_length=1, max_length=4000)]
    user_id: UserIdStr
    session_id: str | None = Field(default=None, description="Optional session context")

    @field_validator("prompt")
    @classmethod
    def block_injection_patterns(cls, v: str) -> str:
        """
        Block known LLM prompt injection markers before they reach the chain.
        Pattern list maintained in src/core/security/injection_patterns.py.
        """
        from src.core.security.injection_patterns import BLOCKED_TOKENS
        lowered = v.lower()
        if any(token in lowered for token in BLOCKED_TOKENS):
            raise ValueError("Prompt contains disallowed instruction patterns.")
        return v

    @property
    def clean_prompt(self) -> str:
        """Collapsed whitespace form — always pass this to the chain, not raw prompt."""
        return " ".join(self.prompt.split())
```

### Response Factory Methods
```python
class AgentResponse(BaseModel):
    content: str
    status: str
    request_id: str
    latency_ms: int | None = None

    @classmethod
    def build_success(cls, content: str, latency_ms: int | None = None) -> "AgentResponse":
        import uuid
        return cls(
            content=content,
            status="success",
            request_id=f"req_{uuid.uuid4().hex[:12]}",
            latency_ms=latency_ms,
        )

    @classmethod
    def build_error(cls, error_code: str) -> "AgentResponse":
        import uuid
        return cls(
            content="",
            status=error_code,
            request_id=f"req_{uuid.uuid4().hex[:12]}",
        )
```

### Settings with pydantic-settings
```python
# src/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # LLM
    OPENAI_API_KEY: str = Field(description="OpenAI API key — never log this")
    LLM_MODEL: str = Field(default="gpt-4o-mini", description="Model to use for completions")
    LLM_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=2.0)

    # App
    ENV: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")
    CACHE_TTL_SECONDS: int = Field(default=300, gt=0)

    # Security
    MAX_PROMPT_LENGTH: int = Field(default=4000, gt=0)

# Module-level singleton — import this everywhere
settings = Settings()
```

---

## LangChain: Production Patterns

### RunnableConfig for Observability
```python
from langchain_core.runnables import RunnableConfig

config = RunnableConfig(
    # Callbacks injected here — e.g. LangSmith tracer, custom logger
    callbacks=[],
    metadata={
        "user_id": payload.user_id,
        "session_id": payload.session_id,
        "environment": settings.ENV,
    },
    tags=["agent-generation", settings.ENV],
    # Token budget guard — raises if chain would exceed this
    max_concurrency=5,
)

output = await pipeline.ainvoke({"query": payload.clean_prompt}, config=config)
```

### Prompt Templates — Externalized
```python
# ❌ AI — prompt text hardcoded in the pipeline factory
prompt = ChatPromptTemplate.from_template("Answer this query: {query}")

# ✅ Human — prompt loaded from file, versioned and editable without code change
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate

PROMPTS_DIR = Path(__file__).parent / "prompts"

def load_agent_prompt(name: str) -> ChatPromptTemplate:
    """
    Load prompt from /prompts/<name>.md.
    Allows prompt iteration without touching Python code.
    """
    template_text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return ChatPromptTemplate.from_template(template_text)

agent_prompt = load_agent_prompt("base_agent")
```

### Structured Output with Pydantic
```python
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

class ExtractedEntities(BaseModel):
    topics: list[str] = Field(description="Main topics discussed in the text")
    sentiment: str = Field(description="Overall sentiment: positive, negative, or neutral")
    action_items: list[str] = Field(default_factory=list)

llm = ChatOpenAI(model=settings.LLM_MODEL, api_key=settings.OPENAI_API_KEY)
structured_llm = llm.with_structured_output(ExtractedEntities)

# Output is now a validated ExtractedEntities instance, not raw text
result: ExtractedEntities = await structured_llm.ainvoke("Analyze this text: {text}")
```

---

## Logging: Structured, Not print()

```python
# src/core/logging.py
import logging
import sys
from src.core.config import settings

def _build_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(settings.LOG_LEVEL)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger

app_logger = _build_logger("app")

# Usage:
app_logger.info("Generation started", extra={"user_id": user_id})
app_logger.error("Pipeline failure", exc_info=exc, extra={"user_id": user_id, "env": settings.ENV})
```

---

## Exception Hierarchy

Don't use bare `Exception` everywhere. Build a typed hierarchy:

```python
# src/core/exceptions.py

class AppBaseError(Exception):
    """Base for all application-level errors."""
    error_code: str = "INTERNAL_ERROR"

class ValidationError(AppBaseError):
    error_code = "VALIDATION_FAILED"

class PipelineError(AppBaseError):
    error_code = "PIPELINE_EXECUTION_FAILED"

class ExternalServiceError(AppBaseError):
    """Raised when a third-party API (OpenAI, Stripe, etc.) fails."""
    error_code = "EXTERNAL_SERVICE_UNAVAILABLE"


# In router — catch by type, not all exceptions
try:
    output = await pipeline.ainvoke(...)
except ExternalServiceError as exc:
    app_logger.warning("LLM call failed", exc_info=exc)
    raise HTTPException(status_code=503, detail="LLM_SERVICE_UNAVAILABLE")
except AppBaseError as exc:
    app_logger.error("Application error", exc_info=exc)
    raise HTTPException(status_code=500, detail=exc.error_code)
```

---

## Testing Hooks (Why DI Matters)

Because everything is injected, tests are trivial:

```python
# tests/test_agent_router.py
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
from main import app
from src.apps.agents.dependencies import get_agent_pipeline

async def mock_pipeline():
    class FakePipeline:
        async def ainvoke(self, inputs, config=None):
            return f"Mock response for: {inputs['query']}"
    return FakePipeline()

app.dependency_overrides[get_agent_pipeline] = mock_pipeline

@pytest.mark.asyncio
async def test_generate_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/v1/agents/generate",
            json={"prompt": "What is 2+2?", "user_id": "usr_abcdefghijklmnop"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

No mocking of `os.environ`, no patching global `llm` objects. One line override.
