import json
from pathlib import Path

import pytest

from app.analysis import (
    backup_event_summary,
    detect_anomalies,
    detect_backup_degradation,
    get_backup_health,
    correlate_signal_series,
    predict_capacity_from_series,
    rank_riskiest_hosts,
)

MOCK_DIR = Path(__file__).parent.parent / "app" / "mocks"


def _load_mock(name: str):
    path = MOCK_DIR / name
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)["result"]


def test_detect_anomalies_rich_data():
    trends = _load_mock("trend.get.json")
    anomalies = detect_anomalies(trends, window=3, threshold=2.0)
    assert anomalies, "anomaly detector should highlight the spike"
    assert any(anomaly["itemid"] == "10001" for anomaly in anomalies)


def test_predict_capacity_can_project():
    trends = _load_mock("trend.get.json")
    projection = predict_capacity_from_series(trends, horizon_hours=24)
    assert projection is not None
    assert "projected" in projection


def test_correlate_signals_pairwise():
    trends = _load_mock("trend.get.json")
    first = [row for row in trends if row["itemid"] == "10001"]
    second = [row for row in trends if row["itemid"] == "10002"]
    correlation = correlate_signal_series(first, second)
    assert correlation
    assert "correlation" in correlation


def test_rank_riskiest_hosts_prefers_backup_events():
    events = _load_mock("event.get.json")
    ranked = rank_riskiest_hosts(events, limit=2, lookback_hours=24)
    assert ranked
    assert ranked[0]["host"].startswith("backup")


def test_backup_health_flags_failures():
    events = _load_mock("event.get.json")
    health = get_backup_health(events, ["backup"])
    assert health["status"] == "degraded"
    assert health["failures"] >= 1


def test_backup_degradation_handles_missing_prior_window():
    events = _load_mock("event.get.json")
    degradation = detect_backup_degradation(events, ["backup"], window_days=1)
    assert "recent_failure_rate" in degradation
    assert "degradation" in degradation
