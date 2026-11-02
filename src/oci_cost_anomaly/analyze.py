"""Load a cost export, run all detectors, build the report."""
from __future__ import annotations

import json
import calendar
from collections import defaultdict
from pathlib import Path

from .detect import Finding, budget_pacing, detect_series


def load_export(path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        assert isinstance(raw.get("daily_costs"), list), "missing 'daily_costs' list"
        return raw
    except (OSError, json.JSONDecodeError, AssertionError) as e:
        raise ValueError(f"cannot load cost export {path}: {e}") from e


def analyze(export: dict, source: str = "export") -> dict:
    by_service: dict[str, list] = defaultdict(list)
    for row in export["daily_costs"]:
        if not isinstance(row, dict) or "date" not in row or "service" not in row or "amount" not in row:
            raise ValueError(f"unusable daily_costs row: {row!r}")
        by_service[str(row["service"])].append(row)
    findings: list[Finding] = []
    services = {}
    for service, points in sorted(by_service.items()):
        points.sort(key=lambda r: r["date"])
        findings += detect_series(points, service)
        services[service] = len(points)
    budget = export.get("budget") or {}
    if budget.get("monthly_amount"):
        month = budget.get("month")  # "YYYY-MM"; default: latest date's month
        dates = sorted(r["date"] for r in export["daily_costs"])
        month = month or dates[-1][:7]
        y, m = int(month[:4]), int(month[5:7])
        dim = calendar.monthrange(y, m)[1]
        mtd_rows = [r for r in export["daily_costs"] if r["date"].startswith(month)]
        if mtd_rows:
            dom = max(int(r["date"][8:10]) for r in mtd_rows)
            f = budget_pacing(sum(float(r["amount"]) for r in mtd_rows), dom, dim,
                              float(budget["monthly_amount"]))
            if f:
                findings.append(f)
    sev_rank = {"high": 2, "medium": 1, "low": 0}
    return {
        "source": source,
        "services": services,
        "findings": [f.__dict__ for f in sorted(
            findings, key=lambda f: (-sev_rank[f.severity], f.service, f.date))],
        "summary": {"services": len(services),
                    "findings": len(findings),
                    "high": sum(1 for f in findings if f.severity == "high"),
                    "medium": sum(1 for f in findings if f.severity == "medium")},
        "limits": ("Statistical screening over a static export, not billing truth: "
                   "no live Cost Analysis API call, no credits/tax handling, "
                   "baselines under 7 days never fire, and a sustained price change "
                   "is flagged once as an anomaly, not learned."),
    }
