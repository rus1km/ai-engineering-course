"""Налаштування з .env через pydantic-settings."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_provider: str = Field(default="openrouter", alias="LLM_PROVIDER")  # 'openrouter' or 'anthropic'

    model_fast: str = Field(default="anthropic/claude-haiku-4-5", alias="MODEL_FAST")
    model_smart: str = Field(default="anthropic/claude-sonnet-4-6", alias="MODEL_SMART")
    model_baseline: str = Field(default="anthropic/claude-sonnet-4-6", alias="MODEL_BASELINE")
    model_judge: str = Field(default="anthropic/claude-sonnet-4-6", alias="MODEL_JUDGE")

    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str | None = Field(default=None, alias="LANGCHAIN_API_KEY")
    langchain_project: str = Field(default="personal-finance-coach", alias="LANGCHAIN_PROJECT")
    langchain_endpoint: str = Field(default="https://api.smith.langchain.com", alias="LANGCHAIN_ENDPOINT")

    transactions_csv: str = Field(default="starter/data/transactions.csv", alias="TRANSACTIONS_CSV")

    app_env: str = Field(default="dev", alias="APP_ENV")
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")
    max_agent_iterations: int = Field(default=6, alias="MAX_AGENT_ITERATIONS")
    llm_timeout_seconds: int = Field(default=30, alias="LLM_TIMEOUT_SECONDS")

    @property
    def transactions_path(self) -> Path:
        p = Path(self.transactions_csv)
        return p if p.is_absolute() else ROOT / p


settings = Settings()
