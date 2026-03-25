from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import ConfigDict, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    zabbix_api_url: HttpUrl = Field(...)
    zabbix_username: str = Field(...)
    zabbix_password: str = Field(...)
    zabbix_verify_ssl: bool = Field(True)
    zabbix_default_group: str = Field("Infrastructure")
    trend_item_ids: List[str] = Field(default_factory=list)
    backup_keywords: List[str] = Field(default_factory=list)
    use_mock_data: bool = Field(False)
    report_horizon_hours: int = Field(6)
    anomaly_std_threshold: float = Field(2.0)
    app_port: int = Field(8000)
    llm_explainer_url: str | None = Field(None)

    @field_validator("trend_item_ids", mode="before")
    def parse_trend_items(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value or []

    @field_validator("backup_keywords", mode="before")
    def parse_backup_keywords(cls, value):
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return [item.lower() for item in (value or [])]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
