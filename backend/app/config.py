"""Process-level configuration (paths, ports). User-editable settings live in the DB (app_settings)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NM_", env_file=PROJECT_ROOT / ".env", extra="ignore")

    data_dir: Path = PROJECT_ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8000
    web_origin: str = "http://localhost:3000"
    session_days: int = 7
    pending_login_minutes: int = 10
    scheduler_enabled: bool = True
    # Tests only: bypasses Windows Credential Manager. Never set this in normal use.
    master_key_override: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "niveshmitra.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


@lru_cache
def get_config() -> Config:
    cfg = Config()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return cfg
