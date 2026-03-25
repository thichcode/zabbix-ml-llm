from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx

from app.config import Settings


class ZabbixClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=str(self.settings.zabbix_api_url).rstrip("/"),
            timeout=30.0,
            verify=self.settings.zabbix_verify_ssl,
            headers={"Content-Type": "application/json-rpc"},
        )
        self.auth_token: str | None = None
        self._group_cache: Dict[str, str] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def call_api(
        self, method: str, params: Dict[str, Any], auth: bool = True
    ) -> Any:
        if self.settings.use_mock_data:
            return self._load_mock(method)

        if auth:
            await self._ensure_auth()

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
        if auth:
            payload["auth"] = self.auth_token

        response = await self._client.post("/api_jsonrpc.php", json=payload)
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            raise RuntimeError(f"Zabbix API error: {result['error']}" )
        return result.get("result", [])

    async def _ensure_auth(self) -> None:
        if self.auth_token:
            return
        payload = {
            "jsonrpc": "2.0",
            "method": "user.login",
            "params": {
                "user": self.settings.zabbix_username,
                "password": self.settings.zabbix_password,
            },
            "id": 1,
        }
        response = await self._client.post("/api_jsonrpc.php", json=payload)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"Zabbix login failed: {data['error']}")
        self.auth_token = data.get("result")

    async def _get_group_id(self, group_name: str) -> Optional[str]:
        if group_name in self._group_cache:
            return self._group_cache[group_name]
        params = {"output": ["groupid"], "filter": {"name": group_name}}
        result = await self.call_api("hostgroup.get", params)
        if not result:
            return None
        group_id = result[0]["groupid"]
        self._group_cache[group_name] = group_id
        return group_id

    def _load_mock(self, method: str) -> Any:
        root = Path(__file__).parent / "mocks"
        filename = root / f"{method}.json"
        if not filename.exists():
            raise FileNotFoundError(f"Mock data for {method} missing")
        with open(filename, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload.get("result", [])

    async def get_hosts(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "output": ["hostid", "host", "name", "status", "available"],
            "selectGroups": ["name"],
            "sortfield": "host",
        }
        if not include_inactive:
            params["filter"] = {"status": 0}
        group_id = await self._get_group_id(self.settings.zabbix_default_group)
        if group_id:
            params["groupids"] = group_id
        return await self.call_api("host.get", params)

    async def get_recent_events(
        self, limit: int = 100, lookback_hours: int = 24
    ) -> List[Dict[str, Any]]:
        now = int(time.time())
        params: Dict[str, Any] = {
            "output": ["eventid", "clock", "value", "severity", "name"],
            "selectHosts": ["host"],
            "sortfield": ["clock"],
            "sortorder": "DESC",
            "time_from": now - lookback_hours * 3600,
            "limit": limit,
        }
        return await self.call_api("event.get", params)

    async def get_trends(
        self,
        itemids: Iterable[str],
        hours: int = 6,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        itemid_list = list(itemids)
        if not itemid_list:
            raise ValueError("At least one itemid is required for trend queries")
        now = int(time.time())
        params = {
            "output": "extend",
            "itemids": itemid_list,
            "time_from": now - hours * 3600,
            "time_till": now,
            "limit": limit,
            "sortfield": "clock",
            "sortorder": "ASC",
        }
        return await self.call_api("trend.get", params)
