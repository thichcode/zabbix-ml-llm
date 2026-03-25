from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analysis import (
    correlate_signal_series,
    detect_anomalies,
    detect_backup_degradation,
    get_backup_health,
    predict_capacity_from_series,
    rank_riskiest_hosts,
)
from app.deps import get_client, settings
from app.reporting import build_sre_report
from app.explainers import explain_report
from app.client import ZabbixClient

router = APIRouter()


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/tools/hosts")
async def get_hosts(include_inactive: bool = Query(False), client: ZabbixClient = Depends(get_client)):
    hosts = await client.get_hosts(include_inactive=include_inactive)
    return {"hosts": hosts, "count": len(hosts)}


@router.get("/tools/events")
async def get_recent_events(
    limit: int = Query(100, ge=1, le=500), client: ZabbixClient = Depends(get_client)
):
    events = await client.get_recent_events(limit=limit)
    return {"events": events, "count": len(events)}


@router.get("/tools/trends")
async def get_trends(
    item_ids: Optional[str] = Query(None),
    hours: int = Query(6, ge=1, le=48),
    limit: int = Query(200, ge=10, le=1000),
    client: ZabbixClient = Depends(get_client),
):
    ids = _parse_csv(item_ids) or settings.trend_item_ids
    if not ids:
        raise HTTPException(status_code=422, detail="Provide at least one item ID for trend queries")
    trends = await client.get_trends(ids, hours=hours, limit=limit)
    return {"item_ids": ids, "trends": trends}


@router.get("/tools/anomalies")
async def detect_anomalies_tool(
    item_ids: Optional[str] = Query(None),
    window: int = Query(6, ge=3, le=24),
    threshold: float = Query(2.0, ge=1.0, le=5.0),
    hours: int = Query(6, ge=1, le=48),
    limit: int = Query(200, ge=10, le=1000),
    client: ZabbixClient = Depends(get_client),
):
    ids = _parse_csv(item_ids) or settings.trend_item_ids
    if not ids:
        raise HTTPException(status_code=422, detail="No trend item IDs configured or provided")
    trends = await client.get_trends(ids, hours=hours, limit=limit)
    anomalies = detect_anomalies(trends, window=window, threshold=threshold)
    return {"anomalies": anomalies, "count": len(anomalies)}


@router.get("/tools/predict_capacity")
async def predict_capacity_tool(
    item_id: str = Query(...),
    hours: int = Query(12, ge=1, le=48),
    horizon_hours: int = Query(24, ge=1, le=168),
    client: ZabbixClient = Depends(get_client),
):
    trends = await client.get_trends([item_id], hours=hours)
    prediction = predict_capacity_from_series(trends, horizon_hours=horizon_hours)
    if not prediction:
        raise HTTPException(status_code=404, detail="Not enough trend data to project capacity")
    return {"prediction": prediction}


@router.get("/tools/correlate_signals")
async def correlate_signals_tool(
    first_item_id: str = Query(...),
    second_item_id: str = Query(...),
    hours: int = Query(6, ge=1, le=48),
    client: ZabbixClient = Depends(get_client),
):
    first = await client.get_trends([first_item_id], hours=hours)
    second = await client.get_trends([second_item_id], hours=hours)
    result = correlate_signal_series(first, second)
    if not result:
        raise HTTPException(status_code=424, detail="Insufficient data for correlation")
    return {"correlation": result}


@router.get("/tools/rank_riskiest_hosts")
async def rank_riskiest_hosts_tool(
    limit: int = Query(5, ge=1, le=20),
    lookback_hours: int = Query(24, ge=1, le=72),
    client: ZabbixClient = Depends(get_client),
):
    events = await client.get_recent_events(limit=500, lookback_hours=lookback_hours)
    ranked = rank_riskiest_hosts(events, limit=limit, lookback_hours=lookback_hours)
    return {"ranked_hosts": ranked}


@router.get("/tools/backup_health")
async def backup_health_tool(client: ZabbixClient = Depends(get_client)):
    events = await client.get_recent_events(limit=500)
    health = get_backup_health(events, settings.backup_keywords or ["backup"])
    return {"backup_health": health}


@router.get("/tools/backup_degradation")
async def backup_degradation_tool(client: ZabbixClient = Depends(get_client)):
    events = await client.get_recent_events(limit=500)
    degradation = detect_backup_degradation(events, settings.backup_keywords or ["backup"])
    return {"backup_degradation": degradation}


@router.get("/sre/report")
async def sre_report(client: ZabbixClient = Depends(get_client)) -> Dict[str, Any]:
    report = await build_sre_report(client, settings)
    return report


@router.get("/sre/explain")
async def sre_explain(client: ZabbixClient = Depends(get_client)) -> Dict[str, str]:
    report = await build_sre_report(client, settings)
    explanation = await explain_report(report, settings)
    return {"explanation": explanation}
