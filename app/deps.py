from __future__ import annotations

from app.client import ZabbixClient
from app.config import get_settings, Settings


settings: Settings = get_settings()
zabbix_client = ZabbixClient(settings)


async def get_client() -> ZabbixClient:
    return zabbix_client


async def close_client() -> None:
    await zabbix_client.close()
