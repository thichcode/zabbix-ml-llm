from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from app.analysis import (
    correlate_signal_series,
    detect_anomalies,
    detect_backup_degradation,
    get_backup_health,
    predict_capacity_from_series,
    rank_riskiest_hosts,
)
from app.client import ZabbixClient
from app.config import Settings


async def build_sre_report(client: ZabbixClient, settings: Settings) -> Dict[str, Any]:
    hosts = await client.get_hosts()
    events = await client.get_recent_events(limit=200)
    trend_data: List[Dict[str, Any]] = []
    if settings.trend_item_ids:
        trend_data = await client.get_trends(settings.trend_item_ids, hours=settings.report_horizon_hours)
    anomalies = detect_anomalies(trend_data, window=6, threshold=settings.anomaly_std_threshold)
    capacity_projection = predict_capacity_from_series(trend_data)
    riskiest_hosts = rank_riskiest_hosts(events)
    correlation = None
    if settings.trend_item_ids and len(settings.trend_item_ids) >= 2:
        grouped_trends: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in trend_data:
            itemid = row.get("itemid")
            if itemid:
                grouped_trends[itemid].append(row)
        grouped = list(grouped_trends.values())
        if len(grouped) >= 2:
            correlation = correlate_signal_series(grouped[0], grouped[1])
    backup_keywords = settings.backup_keywords or ["backup"]
    backup_health = get_backup_health(events, backup_keywords)
    backup_degradation = detect_backup_degradation(events, backup_keywords)

    key_signals = {
        "hosts_monitored": len(hosts),
        "events_last_24h": len(events),
        "anomalies_detected": len(anomalies),
        "backup_health": backup_health.get("status"),
    }

    risk_stack = [f"{entry['host']} (score {entry['score']:.1f})" for entry in riskiest_hosts]
    possible_causes: List[str] = []
    if anomalies:
        possible_causes.append(
            "Statistical spikes on monitored metrics (item ids: {})".format(
                ", ".join({entry["itemid"] for entry in anomalies[:3]})
            )
        )
    if backup_degradation.get("degradation"):
        possible_causes.append("Elevated backup failure rate compared to prior windows.")
    if not possible_causes:
        possible_causes.append("Events align with baseline thresholds and no trending spikes were flagged.")

    recommended_checks: List[str] = []
    if backup_health.get("status") != "ok":
        recommended_checks.append("Inspect backup execution logs on hosts flagged in backup events and verify storage targets.")
    if riskiest_hosts:
        recommended_checks.append(
            "Review alerts on {} to ensure remediation is closing the alert loop.".format(
                ", ".join(entry["host"] for entry in riskiest_hosts[:3])
            )
        )
    if capacity_projection:
        recommended_checks.append(
            "Validate capacity planning for item {} against demand; projected {} after {}h.".format(
                capacity_projection["itemid"],
                round(capacity_projection["projected"], 2),
                capacity_projection["horizon_hours"],
            )
        )
    if not recommended_checks:
        recommended_checks.append("Continue monitoring; no immediate manual checks surfaced.")

    return {
        "summary": "Early warning report anchored to Zabbix host events and trend data.",
        "key_signals": key_signals,
        "trend_analysis": {
            "projection": capacity_projection,
            "anomaly_count": len(anomalies),
            "horizon_hours": settings.report_horizon_hours,
        },
        "risk": risk_stack,
        "correlation": correlation,
        "possible_causes": possible_causes,
        "recommended_checks": recommended_checks,
        "confidence": "High (based on actual Zabbix events/trends).",
        "backup_health": backup_health,
        "backup_degradation": backup_degradation,
        "anomalies": anomalies,
    }
