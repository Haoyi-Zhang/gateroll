#!/usr/bin/env python3
"""Verify supplied snapshots or explicitly report absent optional provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def verify(root: Path) -> dict:
    directory = root / "inputs/public-history"
    source = directory / "public-history-audit.json"
    if not source.is_file():
        return {"schema": "gateroll.public-history-verification.v1", "status": "unavailable",
                "pair_count": None, "failures": [], "pass": None,
                "missing": [str(source)],
                "claim_boundary": "No supplied historical snapshots; controlled pairs are synthetic."}
    manifest = json.loads(source.read_text(encoding="utf-8"))
    failures = []
    for pair in manifest["pairs"]:
        for side in ("old", "new"):
            filename = pair[f"{side}_file"]
            path = (directory / "raw" / filename).resolve()
            if not path.is_relative_to((directory / "raw").resolve()):
                failures.append(f"path:{filename}")
            elif not path.is_file():
                failures.append(f"missing:{filename}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != pair[f"{side}_sha256"]:
                failures.append(f"hash:{filename}")
    return {"schema": "gateroll.public-history-verification.v1",
            "status": "failed" if failures else "verified",
            "pair_count": manifest["pair_count"], "failures": failures,
            "pass": not failures, "claim_boundary": manifest["claim_boundary"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 2 if result["status"] == "unavailable" else (0 if result["pass"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
