from functools import cached_property

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
    case_sensitive=False,
)


# App
class AppSettings(BaseSettings):
    model_config = _ENV
    version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"
    service_name: str = "research-assistant"


# Storage: Postgres
class PostgresSettings(BaseSettings):
    model_config = _ENV
    database_url: PostgresDsn = Field(alias="POSTGRES_DATABASE_URL")

    @cached_property
    def psycopg2_dsn(self) -> str:
        return str(self.database_url).replace("+psycopg2", "")


# Storage: Qdrant + embeddings
class QdrantSettings(BaseSettings):
    model_config = _ENV
    url: str = Field(alias="QDRANT_URL")
    api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    collection: str = Field(default="arxiv_papers", alias="QDRANT_COLLECTION")
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024


# Retrieval: reranker
class RerankerSettings(BaseSettings):
    model_config = _ENV
    model: str = "BAAI/bge-reranker-v2-m3"


# Parsing: Docling
class DoclingSettings(BaseSettings):
    model_config = _ENV
    do_ocr: bool = False
    do_formula_enrichment: bool = True
    generate_picture_images: bool = True
    images_scale: float = 2.0
    num_threads: int = 4
    figure_output_dir: str = "data/figures"


# Parsing: GROBID
class GrobidSettings(BaseSettings):
    model_config = _ENV
    enabled: bool = Field(default=False, alias="GROBID_ENABLED")
    url: str = Field(default="http://localhost:8070", alias="GROBID_URL")
    timeout: int = Field(default=120, alias="GROBID_TIMEOUT")


# Chunking
class ChunkingSettings(BaseSettings):
    model_config = _ENV
    min_chars: int = 20
    merge_max_chars: int = 800
    skip_sections: list[str] = [
        "Table of Contents",
        "List of Figures",
        "List of Tables",
    ]


# LLM
class LLMSettings(BaseSettings):
    model_config = _ENV
    provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    # Gemini free-tier quotas (per Google Cloud project).
    max_rpm: int = Field(default=15, alias="LLM_MAX_RPM")
    max_tpm: int = Field(default=250_000, alias="LLM_MAX_TPM")
    max_rpd: int = Field(default=1_000, alias="LLM_MAX_RPD")
    # Padding added to each request's counted input tokens to cover the response
    # we haven't generated yet, so the TPM check isn't blind to output cost.
    output_token_buffer: int = Field(default=256, alias="LLM_OUTPUT_TOKEN_BUFFER")
    daily_quota_state_path: str = Field(
        default="data/.gemini_quota.json", alias="LLM_QUOTA_STATE_PATH"
    )
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    gemini_model: str = Field(alias="GEMINI_MODEL")


# Reasoning: query router
class ReasoningSettings(BaseSettings):
    model_config = _ENV
    routing_enabled: bool = Field(default=True, alias="ROUTING_ENABLED")
    classifier_confidence_floor: float = Field(
        default=0.5, alias="CLASSIFIER_CONFIDENCE_FLOOR"
    )
    # Falls back to the enrichment model when unset.
    classifier_model: str | None = Field(default=None, alias="CLASSIFIER_MODEL")


# Umbrella
class Settings(BaseSettings):
    model_config = _ENV

    app: AppSettings = Field(default_factory=AppSettings)
    postgres: PostgresSettings = Field(
        default_factory=lambda: PostgresSettings()  # type: ignore[call-arg]
    )
    qdrant: QdrantSettings = Field(
        default_factory=lambda: QdrantSettings()  # type: ignore[call-arg]
    )
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    docling: DoclingSettings = Field(default_factory=DoclingSettings)
    grobid: GrobidSettings = Field(default_factory=GrobidSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    llm: LLMSettings = Field(
        default_factory=lambda: LLMSettings()  # type: ignore[call-arg]
    )
    reasoning: ReasoningSettings = Field(default_factory=ReasoningSettings)


settings = Settings()
