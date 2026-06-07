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
    collection: str = Field(default="arxiv_papers", alias="QDRANT_COLLECTION")
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024


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


# Umbrella
class Settings(BaseSettings):
    model_config = _ENV

    app: AppSettings = Field(default_factory=AppSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    docling: DoclingSettings = Field(default_factory=DoclingSettings)
    grobid: GrobidSettings = Field(default_factory=GrobidSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)


settings = Settings()
