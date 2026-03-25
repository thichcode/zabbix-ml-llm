# Zabbix SRE Copilot

Self-host a deterministic SRE copilot that reads from the Zabbix API, highlights early warnings, and keeps backup/infrastructure risks in focus. The service uses Python + FastAPI, statistical analysis for detection, and exposes a reproducible SRE report without hallucination.

## Architecture

- **FastAPI app** (`app/main.py`) wires the router, dependency injection, and lifecycle hooks.
- **Zabbix client** (`app/client.py`) handles authentication, `host`, `event`, and `trend` queries, plus optional mock data from `app/mocks/` for offline work.
- **Analysis layer** (`app/analysis.py`) performs deterministic math: trend grouping, anomaly detection, correlation, ranking, and backup health/degradation scoring.
- **Reporting layer** (`app/reporting.py`) composes the SRE-ready sections: Summary, Key Signals, Trend Analysis, Risk, Correlation, Possible Causes, Recommended Checks, and Confidence.
- **Optional LLM explainer** (`app/explainers.py`) only activates when `LLM_EXPLAINER_URL` is provided to add natural-language explanation/prioritization without influencing detection.

## Getting started

1. Install deps:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your Zabbix endpoint, credentials, and optional tuning:
   - `ZABBIX_USE_MOCK_DATA=true` keeps the service offline-friendly using `app/mocks/*.json`.
   - `ZABBIX_TREND_ITEM_IDS` powers trend/anomaly utilities when you don't specify IDs on each request.
3. Run the FastAPI server locally:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port ${APP_PORT:-8000}
   ```

## Docker

Build and run the service with Docker Compose:

```bash
cp .env.example .env   # update with real credentials
docker compose build
docker compose up -d
```

The compose file exposes the API on `${APP_PORT}` and mounts `app/mocks` so the container can run offline with the provided fixtures.

## API Endpoints

All endpoints return JSON derived directly from Zabbix data and deterministic calculations.

- `GET /health` – quick liveness check.
- `GET /tools/hosts` – list monitored hosts scoped to the configured group.
- `GET /tools/events?limit=...` – recent events used to power risk ranking.
- `GET /tools/trends?item_ids=1,2&hours=6` – trend points for configured item IDs.
- `GET /tools/anomalies?item_ids=...` – deterministic outlier detection (rolling mean + standard deviation).
- `GET /tools/predict_capacity?item_id=...` – linear regression forecast for a single trend.
- `GET /tools/correlate_signals?first_item_id=...&second_item_id=...` – Pearson correlation score.
- `GET /tools/rank_riskiest_hosts` – severity-weighted ranking of hosts in danger.
- `GET /tools/backup_health` – backup success/failure ratio tied to keyword filtering.
- `GET /tools/backup_degradation` – failure-rate delta between windows.
- `GET /sre/report` – complete SRE-format report (Summary, Key Signals, Trend Analysis, Risk, Correlation, Possible Causes, Recommended Checks, Confidence). This endpoint is the synthesized early-warning narrative.

## SRE Report Format

Each `/sre/report` response includes the mandated sections. For example:

```
Summary: ...
Key Signals: {"hosts_monitored": 12, ...}
Trend Analysis: {...}
Risk: ["db-server (score 8.0)"]
Correlation: {"item_a": 101, ...}
Possible Causes: ["...", "..."]
Recommended Checks: ["...", "..."]
Confidence: High (based on actual Zabbix events/trends).
```

When `LLM_EXPLAINER_URL` is configured, the same report can be spirited into a narrative explanation that still references the deterministic signals (the LLM only translates the facts, it never invents new ones).

## Testing

Use `pytest` to run unit tests and guarantee the statistical tooling behaves as expected.

```bash
pytest
```

Tests cover:

- Analysis helpers (trend building, anomaly scoring, backup health).
- Mock-backed client calls to validate the FastAPI wiring can run offline.

## Mock data

The `app/mocks/` directory includes fixture responses for `host.get`, `event.get`, and `trend.get` so you can develop without a live Zabbix endpoint. Set `ZABBIX_USE_MOCK_DATA=true` in `.env` to use them.

## Contribution

Feel free to add dashboards, more detectors, or richer correlation views. Keep statistical detection deterministic, keep Zabbix the single source of truth, and leave LLMs for explanation/prioritization only.
