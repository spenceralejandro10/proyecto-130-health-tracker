from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Proyecto 130"
    database_url: str = "sqlite:///./data/proyecto130.db"
    api_key: str = ""
    project_length_days: int = 132
    goal_weight_kg: float = 90.0
    project_start_date: date | None = date(2026, 9, 22)
    default_timezone: str = "America/Bogota"
    demo_data: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("project_length_days")
    @classmethod
    def valid_length(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("project_length_days debe ser mayor que 0")
        return value

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.default_timezone)


settings = Settings()


def ensure_runtime_dirs() -> None:
    Path("data").mkdir(exist_ok=True)
    Path("backups").mkdir(exist_ok=True)
