from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CsvTuple = Annotated[tuple[str, ...], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    iris_host: str = "localhost"
    iris_port: int = Field(default=1972, gt=0, le=65535)
    iris_namespace: str = "IRISAPP"
    iris_username: str = "_SYSTEM"
    iris_password: str = "SYS"
    iris_sql_schema: str = "IRISPolitical_Model"
    iris_data_access_mode: Literal["sql", "hybrid"] = "hybrid"

    tse_ckan_base_url: str = "https://dadosabertos.tse.jus.br/api/3/action"
    tse_dataset_id: str = "candidatos-2026"
    tse_portal_url: str = "https://dadosabertos.tse.jus.br/dataset/candidatos-2026"

    camara_base_url: str = "https://dadosabertos.camara.leg.br/api/v2"
    camara_match_start_date: str = "2000-01-01"
    camara_page_size: int = Field(default=100, gt=0, le=100)
    camara_lookback_years: int = Field(default=4, gt=0, le=20)
    camara_max_matched_candidates: int = Field(default=50, gt=0, le=100)
    camara_max_propositions_per_candidate: int = Field(default=50, gt=0, le=1000)
    camara_max_authors_per_proposition: int = Field(default=10, gt=0, le=100)
    camara_http_workers: int = Field(default=6, gt=0, le=16)

    ingest_election_year: int = Field(default=2026, gt=2000)
    ingest_states: CsvTuple = ("SP",)
    ingest_offices: CsvTuple = ("DEPUTADO FEDERAL", "GOVERNADOR")

    http_connect_timeout_seconds: int = Field(default=10, gt=0)
    http_read_timeout_seconds: int = Field(default=60, gt=0)
    http_max_retries: int = Field(default=4, gt=0, le=10)

    chunk_size_tokens: int = Field(default=700, gt=0)
    chunk_overlap_tokens: int = Field(default=100, ge=0)

    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    embedding_batch_size: int = Field(default=50, gt=0, le=100)

    llm_provider: str = "openai"
    llm_api_key: str | None = None
    llm_model: str = "gpt-5-mini"
    llm_max_output_tokens: int = Field(default=4_000, ge=256, le=8_000)

    api_base_url: str = "http://localhost:52773/api"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, gt=0, le=65535)

    def __init__(self, **values: Any) -> None:
        """Accept raw environment-shaped values and let Pydantic validate and coerce them."""
        super().__init__(**values)

    @field_validator("ingest_states", "ingest_offices", mode="before")
    @classmethod
    def parse_csv_tuple(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
            if not items:
                raise ValueError("list cannot be empty")
            return items
        return tuple(value)

    @field_validator("iris_sql_schema")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if not value.replace("_", "").isalnum() or not value[0].isalpha():
            raise ValueError("invalid SQL schema")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> Settings:
        if self.embedding_dimension != 1536:
            raise ValueError("EMBEDDING_DIMENSION must match PoliticalChunk LEN=1536")
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS")
        self._validate_url(self.tse_ckan_base_url, "dadosabertos.tse.jus.br")
        self._validate_url(self.camara_base_url, "dadosabertos.camara.leg.br")
        return self

    @staticmethod
    def _validate_url(value: str, expected_host: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != expected_host:
            raise ValueError(f"URL must use HTTPS host {expected_host}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
