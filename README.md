# oci-cost-anomaly-detector

An **offline cost-anomaly detector** for OCI-style daily cost exports. It reads a JSON export of daily spend per service, screens each service for anomalies with two deterministic detectors, checks month-to-date budget pacing, and reports findings that explain themselves - every number in the message (baseline, z-score, ratio, projection) is the one the rule computed. It **never calls the OCI Cost Analysis API** or any live service.

> **Portfolio project.** The included export is synthetic (45 days x 4 services, 3 injected anomalies). No OCI account or live tenancy was connected or tested. This is statistical screening to triage what to investigate, not billing truth.

## Quickstart

```bash
python -m pip install -e .
oci-cost-anomaly examples/cost-export.json --output report.json
python -m unittest discover -s tests -v
```

Input shape: `{"daily_costs": [{"date": "YYYY-MM-DD", "service": "compute", "amount": 24.13}], "budget": {"monthly_amount": 1400.0, "month": "2026-10"}}` (budget optional). A **project-defined interchange format** - convert your own Cost Analysis export offline. The example export flags exactly the injected anomalies: a compute spike to 71.40 on 2026-10-21 (z +106.6 over a ~24 baseline), an object-storage spike to 19.80 on 2026-10-28 (both detectors), and a networking drop to 0.40 on 2026-10-15 - while the stable database service stays quiet.

## Rules

| Rule | Severity | Meaning |
| --- | --- | --- |
| ANOM001 | high (spike) / medium (drop) | modified z-score over the trailing 14-day median+MAD baseline exceeds 3.5, with an absolute-delta floor of 1.0 so tiny services never fire; flat baselines (MAD=0) get an explicit "break from flat baseline" finding instead of a guessed z |
| ANOM002 | high | day-over-day jump of 3x or more with an absolute rise of at least 5.0 |
| BUDG001 | high | month-to-date projects above 105% of the monthly budget (simple linear pace) |

Design choices kept honest: baselines under 7 days never fire the z-rule (it refuses to guess); the spike rule still fires on short baselines because a 5x jump needs no history; a sustained price change is flagged once, not learned; credits, tax and amortization are out of scope.

`--fail-on high|medium` exits 2 when any finding meets the severity, so CI or a scheduled job can gate on it. Unusable export rows raise a clear error, never a traceback dump.

## Verification in CI

Three gates per push: the unittest suite (12 tests across Python 3.10-3.12), `scripts/eval_gate.py` (7 labeled fixture cases must detect exactly as expected - including negative cases for noise floors, short baselines and on-budget pacing), and a CLI smoke run over the example export asserting the `--fail-on` exit code.

## Honest limits

- Static export analysis: no live Cost Analysis API call, no proof of what any tenancy actually spent.
- MAD-based z is robust screening, not forecasting; it will miss slow leaks and flag legitimate one-off spikes. Both are stated in the findings.
- Budget pacing assumes linear spend and ignores credits/tax.

## References

- Oracle, [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm): the service whose reports this export shape models.
- Iglewicz & Hoaglin's modified z-score (0.6745 factor over MAD): the standard robust outlier statistic used for ANOM001.
