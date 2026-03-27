from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

import os
from pydantic import ConfigDict, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", case_sensitive=False)

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

    @field_validator("use_mock_data", mode="before")
    def parse_mock_flag(cls, value):
        if isinstance(value, str):
            normalized = value.lower()
            if normalized in {"1", "true", "yes", "y"}:
                return True
            if normalized in {"0", "false", "no", "n"}:
                return False
        return bool(value)


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    override = _parse_bool(os.environ.get("ZABBIX_USE_MOCK_DATA"))
    if override is not None:
        settings = settings.model_copy(update={"use_mock_data": override})
    return settings
