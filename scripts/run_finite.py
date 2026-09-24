#!/usr/bin/env python3
"""Run the frozen 12,000-case finite-corpus evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gateroll.evaluate import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--omit-case-corpus", action="store_true")
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    summary = run(root / "inputs", args.output.resolve(), write_cases=not args.omit_case_corpus)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
