"""Deterministic cost-anomaly detection over a daily cost export.

Two detectors, both fully explained in each finding:
- robust z-score: modified z over the trailing window (median + MAD), so one
  spike does not inflate its own baseline;
- day-over-day spike: catches sudden jumps a short window has not absorbed.
Both carry an absolute-delta floor so noise on tiny services never fires.
Budget pacing is simple arithmetic on month-to-date vs pro-rated budget.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

Z_THRESHOLD = 3.5          # standard modified z-score cutoff
WINDOW = 14                # trailing days for the baseline
SPIKE_RATIO = 3.0          # day-over-day jump factor
SPIKE_MIN_ABS = 5.0        # currency units, floors the spike rule
Z_MIN_ABS = 1.0            # currency units, floors the z rule
BUDGET_TOLERANCE = 1.05    # projected month-end may exceed budget by 5%


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    service: str
    date: str
    message: str


def _modified_z(value: float, window: list[float]) -> float | None:
    if len(window) < 7:
        return None  # not enough baseline - never guess
    med = statistics.median(window)
    mad = statistics.median([abs(x - med) for x in window])
    if mad == 0:
        return None if value == med else float("inf")
    return 0.6745 * (value - med) / mad


def detect_series(points: list[dict], service: str,
                  z_k: float = Z_THRESHOLD, min_abs: float = Z_MIN_ABS) -> list[Finding]:
    """points: [{"date": "YYYY-MM-DD", "amount": float}] sorted by date."""
    findings = []
    for i, p in enumerate(points):
        amount, date = float(p["amount"]), p["date"]
        window = [float(q["amount"]) for q in points[max(0, i - WINDOW):i]]
        z = _modified_z(amount, window)
        if z is not None and z != float("inf") and abs(z) > z_k and abs(amount - statistics.median(window)) >= min_abs:
            direction = "spike" if z > 0 else "drop"
            findings.append(Finding(
                "ANOM001", "high" if z > 0 else "medium", service, date,
                f"{service}: {direction} to {amount:.2f} on {date} (baseline median {statistics.median(window):.2f}, modified z {z:+.1f}, cutoff {z_k})"))
        elif z == float("inf") and abs(amount - statistics.median(window)) >= min_abs:
            findings.append(Finding(
                "ANOM001", "high" if amount > statistics.median(window) else "medium", service, date,
                f"{service}: break from flat baseline {statistics.median(window):.2f} to {amount:.2f} on {date}"))
        if i > 0:
            prev = float(points[i - 1]["amount"])
            if prev > 0 and amount > SPIKE_RATIO * prev and (amount - prev) >= SPIKE_MIN_ABS:
                findings.append(Finding(
                    "ANOM002", "high", service, date,
                    f"{service}: day-over-day jump {prev:.2f} -> {amount:.2f} ({amount / prev:.1f}x) on {date}"))
    return findings


def budget_pacing(month_to_date: float, day_of_month: int, days_in_month: int,
                  budget: float, service: str = "all-services") -> Finding | None:
    if not (budget > 0 and 1 <= day_of_month <= days_in_month):
        return None
    projected = month_to_date / day_of_month * days_in_month
    if projected > budget * BUDGET_TOLERANCE:
        return Finding(
            "BUDG001", "high", service, f"day-{day_of_month}",
            f"{service}: month-to-date {month_to_date:.2f} on day {day_of_month}/{days_in_month} "
            f"projects to {projected:.2f}, {projected / budget * 100:.0f}% of the {budget:.2f} budget")
    return None
