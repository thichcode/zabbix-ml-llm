from __future__ import annotations

from fastapi import FastAPI

from app.deps import close_client
from app.router import router

app = FastAPI(
    title="Zabbix SRE Copilot",
    description="Self-hosted SRE copilot using deterministic analysis powered by Zabbix.",
    version="0.1.0",
)
app.include_router(router)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await close_client()
