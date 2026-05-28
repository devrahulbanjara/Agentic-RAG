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
    dense_model: str = "BAAI/bge-small-en"
    sparse_model: str = "qdrant/bm25"
    embedding_dim: int = 384


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
    sleep_seconds: float = Field(default=13.0, alias="LLM_SLEEP_SECONDS")
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
