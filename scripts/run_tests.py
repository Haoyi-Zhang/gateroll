#!/usr/bin/env python3
"""Run the artifact's standard-library test suite."""
from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--results", type=Path)
    parser.add_argument("--skip-runtime-preflight", action="store_true")
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    if args.results is not None:
        os.environ["GATEROLL_RESULTS"] = str(args.results.resolve())
    pattern = "test_*.py"
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern=pattern, top_level_dir=str(root))
    if args.skip_runtime_preflight:
        filtered = unittest.TestSuite()
        for group in suite:
            for inner in group:
                if "test_runtime_preflight" not in str(inner):
                    filtered.addTest(inner)
        suite = filtered
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
