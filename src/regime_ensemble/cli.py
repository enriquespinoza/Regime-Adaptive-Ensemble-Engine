"""Read a frozen bundle and policy and print or save an auditable research decision."""

import argparse
import json
import sys
from pathlib import Path

from .core import ContractError, evaluate


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only regime ensemble evaluator")
    parser.add_argument("--input", type=Path, required=True, help="ensemble_run_v1 JSON bundle")
    parser.add_argument("--policy", type=Path, required=True, help="ensemble_policy_v1 JSON")
    parser.add_argument("--output", type=Path, help="Optional output artifact path")
    args = parser.parse_args()
    try:
        run = json.loads(args.input.read_text(encoding="utf-8"))
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        result = evaluate(run, policy)
    except (OSError, ValueError, ContractError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 2
    report = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0 if result["status"] == "RESEARCH_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
