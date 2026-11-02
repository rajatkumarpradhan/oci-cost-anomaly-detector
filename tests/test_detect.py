"""Detector math, floors, budget pacing and report shape."""
import unittest
from pathlib import Path

from oci_cost_anomaly import analyze, budget_pacing, detect_series, load_export

FIXTURES = Path(__file__).resolve().parents[1] / "examples"


def series(n, amount=10.0, spike_at=None, spike_amount=50.0):
    pts = [{"date": f"2026-10-{d:02d}", "amount": amount} for d in range(1, n + 1)]
    if spike_at:
        pts[spike_at - 1]["amount"] = spike_amount
    return pts


class ZRuleTests(unittest.TestCase):
    def test_spike_fires_with_date_and_baseline_in_message(self):
        pts = [{"date": f"2026-10-{d:02d}", "amount": 10.0 + (d % 3) * 0.2} for d in range(1, 21)]
        pts[14]["amount"] = 40.0
        f = detect_series(pts, "compute")
        z = [x for x in f if x.rule == "ANOM001"]
        self.assertEqual(len(z), 1)
        self.assertEqual(z[0].date, "2026-10-15")
        self.assertIn("modified z", z[0].message)
        self.assertEqual(z[0].severity, "high")

    def test_flat_baseline_break_fires(self):
        pts = series(20, amount=10.0, spike_at=15, spike_amount=25.0)
        f = [x for x in detect_series(pts, "s") if x.rule == "ANOM001"]
        self.assertEqual(len(f), 1)
        self.assertIn("flat baseline", f[0].message)

    def test_noise_below_absolute_floor_never_fires(self):
        pts = series(20, amount=0.1, spike_at=15, spike_amount=0.8)
        self.assertEqual([x for x in detect_series(pts, "s") if x.rule == "ANOM001"], [])

    def test_under_seven_days_baseline_never_fires_z(self):
        pts = series(6, spike_at=4, spike_amount=11.5)  # small rise: no spike rule, z must not guess
        self.assertEqual(detect_series(pts, "s"), [])

    def test_gradual_trend_does_not_fire(self):
        pts = [{"date": f"2026-10-{d:02d}", "amount": 10.0 + d * 0.3} for d in range(1, 21)]
        self.assertEqual(detect_series(pts, "s"), [])


class SpikeRuleTests(unittest.TestCase):
    def test_day_over_day_jump(self):
        f = [x for x in detect_series(series(6, spike_at=4, spike_amount=50.0), "s")
             if x.rule == "ANOM002"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].date, "2026-10-04")
        self.assertIn("5.0x", f[0].message)

    def test_jump_below_ratio_or_floor_quiet(self):
        self.assertEqual([x for x in detect_series(series(6, spike_at=4, spike_amount=12.0), "s")
                          if x.rule == "ANOM002"], [])       # 1.2x
        self.assertEqual([x for x in detect_series(series(6, amount=1.0, spike_at=4, spike_amount=3.5), "s")
                          if x.rule == "ANOM002"], [])       # 3.5x but delta 2.5 < floor


class BudgetPacingTests(unittest.TestCase):
    def test_breach_and_ok(self):
        f = budget_pacing(900.0, 10, 31, 1500.0)
        self.assertIsNotNone(f)
        self.assertEqual(f.rule, "BUDG001")
        self.assertIn("projects to 2790.00", f.message)
        self.assertIsNone(budget_pacing(400.0, 10, 31, 1500.0))

    def test_degenerate_inputs_never_fire(self):
        self.assertIsNone(budget_pacing(900.0, 0, 31, 1500.0))
        self.assertIsNone(budget_pacing(900.0, 10, 31, 0.0))


class ReportTests(unittest.TestCase):
    def test_example_export_finds_injected_anomalies(self):
        report = analyze(load_export(FIXTURES / "cost-export.json"), "cost-export.json")
        self.assertEqual(report["services"], {"compute": 45, "database": 45,
                                              "networking": 45, "object-storage": 45})
        hits = {(f["service"], f["date"]) for f in report["findings"]}
        self.assertIn(("compute", "2026-10-21"), hits)
        self.assertIn(("object-storage", "2026-10-28"), hits)
        self.assertIn(("networking", "2026-10-15"), hits)
        self.assertTrue(all("cost-export.json" == report["source"] for _ in [0]))
        self.assertIn("not billing truth", report["limits"])
        # stable database service must stay quiet
        self.assertNotIn("database", {f["service"] for f in report["findings"]})

    def test_bad_row_is_an_error_not_a_crash_trace(self):
        with self.assertRaises(ValueError):
            analyze({"daily_costs": [{"date": "2026-10-01"}]})
        with self.assertRaises(ValueError):
            load_export(FIXTURES / "does-not-exist.json")


if __name__ == "__main__":
    unittest.main()
