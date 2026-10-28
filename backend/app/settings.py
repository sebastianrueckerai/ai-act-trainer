from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.corpus.excerpt import DEFAULT_BUDGET

DEFAULT_SECRET = "dev-secret-change-me-before-production"
HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    secret_key: str = Field(default=DEFAULT_SECRET, min_length=16)

    database_url: str = "sqlite:///./trainer.db"
    run_migrations: bool = True

    auth_backend: Literal["dev", "invite", "oidc", "ldap", "proxy"] = "dev"
    admin_groups: Annotated[list[str], NoDecode] = ["compliance"]
    proxy_trusted_addresses: Annotated[list[str], NoDecode] = []
    session_max_age_seconds: int = 43200
    guest_access: bool = False
    guest_seats: int = 10
    guest_retention_hours: int = 6
    public_url: str = "http://localhost:8000"

    llm_base_url: str = "http://localhost:4000/v1"
    llm_api_key: str = "sk-dev"
    # A proxy key that may create keys and read spend. Empty turns budgets off.
    litellm_admin_key: str = ""
    llm_model_strong: str = "strong"
    llm_model_fast: str = "fast"
    llm_model_embed: str | None = None
    llm_timeout_seconds: float = 60.0
    excerpt_budget_chars: int = DEFAULT_BUDGET
    search_top_k: int = 5
    compact_tokens: int = 6000
    persona_model_role: Literal["strong", "fast"] = "strong"
    # The wall clock a turn may spend on critic retries before it ships what it has.
    turn_budget_seconds: float = 20.0

    data_level: Literal[0, 1, 2] = 0
    retention_days: int = 30
    retrain_on_major_version: bool = True
    training_interval_days: int = 365

    # The spend guard: every streamed turn is metered, and a rolling day closes at
    # these caps, so no visitor can drive model spend without bound.
    turn_limit_user_day: int = 300
    turn_limit_guest_day: int = 150
    turn_limit_global_day: int = 2000

    feature_admin_view: bool = False
    feature_certificate: bool = False
    feature_reminders: bool = False
    feature_department_stats: bool = False
    feature_audit_log: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    theme_primary: str = Field(default="#38bdf8", pattern=HEX_COLOR)
    theme_secondary: str = Field(default="#16233a", pattern=HEX_COLOR)
    theme_accent: str = Field(default="#fbbf24", pattern=HEX_COLOR)
    theme_background: str = Field(default="#f8fafc", pattern=HEX_COLOR)
    theme_look: Literal["pixel", "clean"] = "pixel"

    content_dir: Path = REPO_ROOT / "content"
    content_overlay_dir: Path | None = None
    personas_dir: Path = REPO_ROOT / "personas"
    corpus_dir: Path = REPO_ROOT / "corpus"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    fonts_dir: Path = REPO_ROOT / "frontend" / "src" / "assets" / "fonts"

    @field_validator("admin_groups", "proxy_trusted_addresses", mode="before")
    @classmethod
    def split_commas(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator(
        "content_overlay_dir",
        "llm_model_embed",
        "smtp_host",
        "smtp_user",
        "smtp_password",
        "smtp_from",
        mode="before",
    )
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator(
        "content_dir", "personas_dir", "corpus_dir", "frontend_dist", "fonts_dir", mode="before"
    )
    @classmethod
    def reject_empty_path(cls, value: object) -> object:
        if value == "":
            raise ValueError("must not be empty; unset the variable to use the default")
        return value

    @field_validator("data_level", mode="before")
    @classmethod
    def data_level_accepts_numeric_strings(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
        return value

    @model_validator(mode="after")
    def check_consistency(self) -> "Settings":
        problems: list[str] = []
        if self.env == "production" and self.auth_backend == "dev":
            problems.append("AUTH_BACKEND=dev is not allowed when ENV=production")
        if self.env == "production" and self.secret_key == DEFAULT_SECRET:
            problems.append("SECRET_KEY must be set when ENV=production")
        if self.feature_audit_log and self.data_level < 2:
            problems.append("FEATURE_AUDIT_LOG requires DATA_LEVEL=2")
        if self.feature_reminders and not self.smtp_host:
            problems.append("FEATURE_REMINDERS requires SMTP_HOST")
        if self.auth_backend == "proxy" and not self.proxy_trusted_addresses:
            problems.append("AUTH_BACKEND=proxy requires PROXY_TRUSTED_ADDRESSES")
        if self.auth_backend == "invite" and not self.litellm_admin_key:
            problems.append("AUTH_BACKEND=invite requires LITELLM_ADMIN_KEY")
        if problems:
            raise ValueError("configuration problems: " + "; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
