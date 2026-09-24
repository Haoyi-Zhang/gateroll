#!/usr/bin/env python3
"""Verify a reproduced semantic summary against the frozen expected result."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def compare(expected: Any, actual: Any, path: str = "root") -> list[str]:
    errors: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}"]
        if set(expected) != set(actual):
            errors.append(f"{path}: key mismatch expected={sorted(expected)} actual={sorted(actual)}")
        for key in sorted(set(expected) & set(actual)):
            errors.extend(compare(expected[key], actual[key], f"{path}.{key}"))
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            errors.append(f"{path}: list mismatch")
        else:
            for index, (left, right) in enumerate(zip(expected, actual)):
                errors.extend(compare(left, right, f"{path}[{index}]"))
    elif isinstance(expected, float):
        if not isinstance(actual, (int, float)) or not math.isclose(expected, float(actual), rel_tol=1e-12, abs_tol=1e-12):
            errors.append(f"{path}: expected {expected!r}, got {actual!r}")
    elif expected != actual:
        errors.append(f"{path}: expected {expected!r}, got {actual!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    actual = json.loads(args.actual.read_text(encoding="utf-8"))
    errors = compare(expected, actual)
    report = {
        "semantic_match": not errors,
        "differences": errors,
        "finite_cases": actual.get("finite", {}).get("cases"),
        "campaigns": actual.get("runtime", {}).get("campaigns"),
        "strategy_runs": actual.get("runtime", {}).get("strategy_runs"),
        "transaction_records": actual.get("runtime", {}).get("transaction_records"),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
