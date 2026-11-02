import argparse
import json
from pathlib import Path

from .analyze import analyze, load_export


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline OCI cost-anomaly detection over a daily cost export")
    parser.add_argument("export", help="JSON cost export, e.g. examples/cost-export.json")
    parser.add_argument("--output", help="report JSON path; default stdout")
    parser.add_argument("--fail-on", choices=["high", "medium"],
                        help="exit 2 when any finding meets or beats this severity")
    args = parser.parse_args(argv)
    try:
        report = analyze(load_export(args.export), Path(args.export).name)
    except ValueError as exc:
        parser.error(str(exc))
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.fail_on:
        rank = {"high": 2, "medium": 1}
        if any(rank.get(f["severity"], 0) >= rank[args.fail_on] for f in report["findings"]):
            return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
