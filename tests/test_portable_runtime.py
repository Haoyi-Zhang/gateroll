from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

from gateroll.portable_runtime import WindowsJob, filesystem_path, fresh_directory, private_path
from gateroll.rpcutil import atomic_json, call
from scripts.verify_public_history import verify
from scripts.run_interrupted_dual_write import execute as interrupted_control
from reproduce_base import run_step

ROOT = Path(__file__).resolve().parents[1]


class PortableRuntimeTests(unittest.TestCase):
    def test_unknown_and_historical_outputs_are_refused(self):
        for path in (ROOT, ROOT.parent, ROOT / "results/raw/campaigns",
                     ROOT / "results/runtime_reproductions"):
            with self.assertRaises(ValueError):
                private_path(ROOT, path)
        directory = fresh_directory(ROOT, ROOT / "results/runtime_reproductions" / f"path-test-{uuid.uuid4().hex}")
        marker = directory / "keep.json"
        atomic_json(marker, {"original": True})
        with self.assertRaises(FileExistsError):
            fresh_directory(ROOT, directory)
        self.assertEqual(json.loads(marker.read_text(encoding="utf-8")), {"original": True})

    def test_missing_history_is_not_a_pass(self):
        directory = fresh_directory(ROOT, ROOT / "results/runtime_reproductions" / f"history-test-{uuid.uuid4().hex}")
        result = verify(directory)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["pass"])

    def test_long_owned_path_preserves_atomic_state(self):
        directory = fresh_directory(ROOT, ROOT / "results/runtime_reproductions" / f"long-path-test-{uuid.uuid4().hex}")
        path = directory / ("bounded-" + "x" * 70) / "state.json"
        atomic_json(path, {"value": 7})
        self.assertEqual(json.loads(filesystem_path(path).read_text(encoding="utf-8")), {"value": 7})

    def test_mechanism_off_control_retains_partial_dual_write_failure(self):
        output = ROOT / "results/runtime_reproductions" / f"interrupted-test-{uuid.uuid4().hex}"
        result = interrupted_control(ROOT, output)
        self.assertFalse(result["pending_dual_write_enabled"])
        self.assertFalse(result["partial_response"]["available"])
        self.assertFalse(result["replica_values_agree"])
        self.assertEqual(result["primary_read_response"]["value"], 12)
        self.assertEqual(result["read_response"]["value"], 11)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object test")
    def test_reproduction_step_runs_nested_campaigns(self):
        directory = fresh_directory(ROOT, ROOT / "results/runtime_reproductions" / f"nested-matrix-test-{uuid.uuid4().hex}")
        output = directory / "campaigns"
        result = run_step("campaign-matrix", [
            sys.executable, "-B", "-m", "scripts.run_campaign_matrix",
            "--artifact-root", str(ROOT), "--output", str(output),
            "--workers", "2", "--start", "0", "--end", "1",
        ], ROOT, directory, 60)
        summary = json.loads((output / "campaign_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(summary["strategy_runs"], 6)
        self.assertEqual(summary["transaction_records"], 216)
        self.assertEqual(summary["strategies"]["certified"]["semantic_violations"], 0)
        atomic_json(directory / "result.json", result)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object test")
    def test_reproduction_step_timeout_closes_owned_subtree(self):
        directory = fresh_directory(ROOT, ROOT / "results/runtime_reproductions" / f"step-test-{uuid.uuid4().hex}")
        info = directory / "info.json"
        with self.assertRaises(subprocess.TimeoutExpired):
            run_step("fixture", [sys.executable, "-B", "-m", "tests.owned_process_fixture",
                                "--gate", str(directory / "fixture.gate.json"), "--info", str(info)],
                     ROOT, directory, 1.5)
        self.assertTrue(info.is_file(), "fixture must have spawned its child before timeout")
        port = json.loads(info.read_text(encoding="utf-8"))["port"]
        with self.assertRaises((OSError, ConnectionError)):
            call(port, {"cmd": "health"}, timeout=0.2)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object test")
    def test_timeout_kills_owned_localhost_descendant(self):
        directory = fresh_directory(ROOT, ROOT / "results/runtime_reproductions" / f"job-test-{uuid.uuid4().hex}")
        gate, info = directory / "gate.json", directory / "info.json"
        owner = None
        with (directory / "fixture.stdout").open("x") as stdout, (directory / "fixture.stderr").open("x") as stderr:
            process = subprocess.Popen(
                [sys.executable, "-B", "-m", "tests.owned_process_fixture",
                 "--gate", str(gate), "--info", str(info)], cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                owner = WindowsJob(process)
                atomic_json(gate, {"ready": True})
                deadline = time.monotonic() + 15
                while not info.exists():
                    if time.monotonic() > deadline or process.poll() is not None:
                        self.fail("owned fixture did not become healthy")
                    time.sleep(0.02)
                port = json.loads(info.read_text(encoding="utf-8"))["port"]
                self.assertTrue(call(port, {"cmd": "health"})["ok"])
                owner.close()
                process.wait(timeout=5)
                deadline = time.monotonic() + 3
                while True:
                    try:
                        call(port, {"cmd": "health"}, timeout=0.1)
                    except (OSError, ConnectionError):
                        break
                    if time.monotonic() > deadline:
                        self.fail("owned localhost descendant survived job close")
                    time.sleep(0.02)
                atomic_json(directory / "result.json", {"owned_descendant_stopped": True})
            finally:
                if owner is not None:
                    owner.close()
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
