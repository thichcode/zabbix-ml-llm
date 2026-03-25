from __future__ import annotations

import math
import statistics
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple


SEVERITY_WEIGHTS: Dict[int, float] = {0: 1.0, 1: 1.25, 2: 1.5, 3: 2.0, 4: 2.75, 5: 3.5}


def build_trend_series(trend_rows: Iterable[Dict[str, Any]]) -> Dict[str, List[Tuple[int, float]]]:
    series: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
    for row in trend_rows:
        itemid = str(row.get("itemid"))
        if not itemid:
            continue
        clock = int(row.get("clock") or time.time())
        raw_value = row.get("value_avg") or row.get("value_min") or row.get("value_max") or row.get("value") or 0
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        series[itemid].append((clock, value))
    for points in series.values():
        points.sort()
    return series


def detect_anomalies(
    trend_rows: Iterable[Dict[str, Any]],
    window: int = 6,
    threshold: float = 2.0,
) -> List[Dict[str, Any]]:
    anomalies: List[Dict[str, Any]] = []
    series = build_trend_series(trend_rows)
    for itemid, points in series.items():
        values = [value for _, value in points]
        for idx in range(window, len(values)):
            window_values = values[idx - window : idx]
            if len(window_values) < 2:
                continue
            baseline = statistics.mean(window_values)
            try:
                deviation = statistics.stdev(window_values)
            except statistics.StatisticsError:
                continue
            if deviation == 0:
                continue
            magnitude = abs(values[idx] - baseline)
            if magnitude > threshold * deviation:
                anomalies.append(
                    {
                        "itemid": itemid,
                        "timestamp": points[idx][0],
                        "value": values[idx],
                        "baseline": baseline,
                        "deviation": deviation,
                        "score": magnitude / deviation,
                    }
                )
    return anomalies


def linear_regression(x: List[float], y: List[float]) -> Tuple[float, float]:
    if not x or not y or len(x) != len(y):
        return 0.0, 0.0
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denominator = sum((xi - mean_x) ** 2 for xi in x)
    if denominator == 0:
        return 0.0, mean_y
    slope = numerator / denominator
    intercept = mean_y - slope * mean_x
    return slope, intercept


def predict_capacity_from_series(
    trend_rows: Iterable[Dict[str, Any]], horizon_hours: int = 24
) -> Dict[str, Any] | None:
    series = build_trend_series(trend_rows)
    predictions: List[Dict[str, Any]] = []
    for itemid, points in series.items():
        if len(points) < 3:
            continue
        baseline = points[0][0]
        x = [((clock - baseline) / 3600) for clock, _ in points]
        y = [value for _, value in points]
        slope, intercept = linear_regression(x, y)
        last_x = x[-1]
        projected_value = slope * (last_x + horizon_hours) + intercept
        predictions.append(
            {
                "itemid": itemid,
                "current": y[-1],
                "projected": projected_value,
                "slope": slope,
                "horizon_hours": horizon_hours,
            }
        )
    if not predictions:
        return None
    # Return the most active item (largest positive slope magnitude)
    return max(predictions, key=lambda entry: abs(entry["slope"]))


def correlate_signal_series(
    trend_rows_a: Iterable[Dict[str, Any]], trend_rows_b: Iterable[Dict[str, Any]]
) -> Dict[str, Any] | None:
    series_a = build_trend_series(trend_rows_a)
    series_b = build_trend_series(trend_rows_b)
    if not series_a or not series_b:
        return None
    item_a, points_a = next(iter(series_a.items()))
    item_b, points_b = next(iter(series_b.items()))
    values_map_b = {clock: value for clock, value in points_b}
    paired: List[Tuple[float, float]] = []
    for clock, value in points_a:
        if clock in values_map_b:
            paired.append((value, values_map_b[clock]))
    if len(paired) < 3:
        return None
    xs, ys = zip(*paired)
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in paired)
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    correlation = cov / math.sqrt(var_x * var_y)
    return {
        "item_a": item_a,
        "item_b": item_b,
        "correlation": correlation,
        "samples": len(paired),
    }


def rank_riskiest_hosts(
    events: Iterable[Dict[str, Any]], limit: int = 5, lookback_hours: int = 24
) -> List[Dict[str, Any]]:
    now = time.time()
    cutoff = now - lookback_hours * 3600
    host_scores: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"score": 0.0, "events": 0, "severity": 0}
    )
    filtered_events = [
        event for event in events if int(event.get("clock", 0)) >= cutoff
    ]
    if not filtered_events:
        filtered_events = list(events)
    for event in filtered_events:
        clock = int(event.get("clock", 0))
        severity = int(event.get("severity", 0))
        weight = SEVERITY_WEIGHTS.get(severity, 1.0)
        for host in event.get("hosts", []):
            host_name = host.get("host") or host.get("name") or "unknown"
            host_record = host_scores[host_name]
            host_record["score"] += weight
            host_record["events"] += 1
            host_record["severity"] = max(host_record["severity"], severity)
    ranked = sorted(
        [
            {"host": host, **data}
            for host, data in host_scores.items()
            if data["events"] > 0
        ],
        key=lambda record: (record["score"], record["severity"], record["events"]),
        reverse=True,
    )
    return ranked[:limit]


def backup_event_summary(events: Iterable[Dict[str, Any]], keywords: Iterable[str]) -> List[Dict[str, Any]]:
    keywords_set = {keyword.lower() for keyword in keywords}
    matches: List[Dict[str, Any]] = []
    for event in events:
        text = (event.get("name") or "").lower()
        hosts = " ".join([host.get("host", "") for host in event.get("hosts", [])]).lower()
        if keywords_set and not any(keyword in text or keyword in hosts for keyword in keywords_set):
            continue
        matches.append(event)
    return matches


def get_backup_health(events: Iterable[Dict[str, Any]], keywords: Iterable[str]) -> Dict[str, Any]:
    matches = backup_event_summary(events, keywords)
    total = len(matches)
    if total == 0:
        return {"status": "unknown", "details": "no backup events found"}
    failures = sum(1 for event in matches if str(event.get("value")) == "1")
    success = total - failures
    health_score = 100 * (success / total)
    return {
        "status": "ok" if health_score >= 90 else "warning" if health_score >= 75 else "degraded",
        "success_rate": round(health_score, 1),
        "failures": failures,
        "total_events": total,
    }


def detect_backup_degradation(
    events: Iterable[Dict[str, Any]], keywords: Iterable[str], window_days: int = 2
) -> Dict[str, Any]:
    matches = backup_event_summary(events, keywords)
    if not matches:
        return {"status": "unknown", "details": "no backup events"}
    now = time.time()
    window_seconds = window_days * 86400
    recent = [
        event
        for event in matches
        if int(event.get("clock", 0)) >= now - window_seconds
    ]
    prior = [
        event
        for event in matches
        if now - 2 * window_seconds <= int(event.get("clock", 0)) < now - window_seconds
    ]
    def failure_rate(batch: List[Dict[str, Any]]) -> float:
        if not batch:
            return 0.0
        return sum(1 for e in batch if str(e.get("value")) == "1") / len(batch)
    recent_rate = failure_rate(recent)
    prior_rate = failure_rate(prior)
    degradation = recent_rate > prior_rate and recent_rate >= 0.1
    return {
        "recent_failure_rate": round(recent_rate, 3),
        "prior_failure_rate": round(prior_rate, 3),
        "degradation": degradation,
        "detail": "failure rate increased" if degradation else "stable",
    }
