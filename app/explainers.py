from __future__ import annotations

import httpx
from typing import Any, Dict

from app.config import Settings


async def explain_report(report: Dict[str, Any], settings: Settings) -> str:
    key_signals = report.get("key_signals", {}) or {}
    risks = report.get("risk", []) or []
    signal_summary = ", ".join(
        f"{name}={value}" for name, value in key_signals.items()
    )
    base = (
        f"Summary: {report.get('summary', 'no summary')}\n"
        f"Key signals: {signal_summary if signal_summary else 'none'}\n"
        f"Risk stack: {', '.join(risks) if risks else 'not reported'}"
    )
    if settings.llm_explainer_url:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {
                "report": report,
                "prompt": "Explain this SRE early warning report and prioritize checks.",
            }
            response = await client.post(settings.llm_explainer_url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("text") or base
    return base
