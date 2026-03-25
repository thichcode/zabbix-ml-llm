import pytest

from app.client import ZabbixClient
from app.config import Settings


@pytest.mark.asyncio
async def test_zabbix_client_mock():
    settings = Settings(
        zabbix_api_url="https://mock.zabbix",
        zabbix_username="user",
        zabbix_password="pass",
        use_mock_data=True,
    )
    client = ZabbixClient(settings)
    hosts = await client.get_hosts()
    events = await client.get_recent_events()
    trends = await client.get_trends(["10001"], hours=6)
    assert hosts
    assert isinstance(hosts, list)
    assert events
    assert trends
    await client.close()
