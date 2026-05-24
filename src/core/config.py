from functools import cached_property

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"
    service_name: str = "research-assistant"

    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_database_url: PostgresDsn = Field(alias="POSTGRES_DATABASE_URL")
    postgres_echo_sql: bool = Field(default=False, alias="POSTGRES_ECHO_SQL")
    postgres_pool_size: int = Field(default=20, alias="POSTGRES_POOL_SIZE")
    postgres_max_overflow: int = Field(default=0, alias="POSTGRES_MAX_OVERFLOW")

    qdrant_url: str = Field(alias="QDRANT_URL")
    qdrant_collection: str = Field(alias="QDRANT_COLLECTION")

    dense_model: str = "BAAI/bge-small-en"
    sparse_model: str = "qdrant/bm25"

    @cached_property
    def postgres_psycopg2_dsn(self) -> str:
        return str(self.postgres_database_url).replace("+psycopg2", "")


settings = Settings()
