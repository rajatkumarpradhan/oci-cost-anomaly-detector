"""Detection eval gate: labeled fixture cases must produce exactly the expected rules."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oci_cost_anomaly import analyze

def main() -> int:
    fixture = json.loads((Path(__file__).resolve().parents[1] / "examples" / "eval-fixture.json").read_text())
    failures = 0
    for i, case in enumerate(fixture["cases"], 1):
        export = {"daily_costs": [dict(p, service="svc") for p in case["points"]]}
        if case.get("budget"):
            export["budget"] = case["budget"]
        report = analyze(export, "eval-fixture")
        got = sorted({f["rule"] for f in report["findings"]})
        want = sorted(case["expect_rules"])
        problems = [] if got == want else [f"rules: expected {want}, got {got}"]
        if case.get("expect_date"):
            dates = {f["date"] for f in report["findings"]}
            if dates != {case["expect_date"]}:
                problems.append(f"dates: expected only {case['expect_date']}, got {sorted(dates)}")
        failures += bool(problems)
        print(f"{'PASS' if not problems else 'FAIL'} case {i}: {case['name']}")
        for p in problems:
            print(f"      {p}")
    print(f"eval gate: {len(fixture['cases']) - failures}/{len(fixture['cases'])} cases detected as expected")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
