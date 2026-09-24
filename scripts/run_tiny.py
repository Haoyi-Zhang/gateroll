#!/usr/bin/env python3
"""Exhaustively enumerate the frozen two-service fragment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gateroll.tiny_exhaustive import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.output.resolve())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
