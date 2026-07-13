from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import authorization, load_script


def process_identity(pid: int) -> tuple[str, str]:
    stat = (Path("/proc") / str(pid) / "stat").read_text().split()
    start_ticks = stat[21]
    command = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    return start_ticks, hashlib.sha256(command).hexdigest()


class CleanupAndSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.init = load_script("init_goal_run.py")
        self.record_handle = load_script("record_runtime_handle.py")
        self.cleanup = load_script("reclaim_runtime_handles.py")
        self.sync = load_script("finalize_goal_sync.py")

    def test_cleanup_stops_only_matching_run_owned_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            process = subprocess.Popen(["/bin/sleep", "30"])
            try:
                recorded = self.record_handle.record_runtime_handle(
                    authorization("goal-dispatch", "evidence.record"),
                    run_dir,
                    pid=process.pid,
                )
                self.assertTrue(recorded["ok"])
                result = self.cleanup.reclaim_runtime_handles(
                    authorization("goal-close", "runtime.cleanup"),
                    run_dir,
                    grace_seconds=0.2,
                )
                self.assertTrue(result["ok"])
                process.wait(timeout=2)
                self.assertIsNotNone(process.returncode)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_cleanup_refuses_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            process = subprocess.Popen(["/bin/sleep", "30"])
            try:
                start_ticks, _ = process_identity(process.pid)
                (run_dir / "runtime_handles.jsonl").write_text(
                    json.dumps(
                        {
                            "pid": process.pid,
                            "process_start_ticks": start_ticks,
                            "command_hash": "0" * 64,
                            "status": "active",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                result = self.cleanup.reclaim_runtime_handles(
                    authorization("goal-close", "runtime.cleanup"),
                    run_dir,
                    grace_seconds=0.1,
                )
                self.assertFalse(result["ok"])
                self.assertIsNone(process.poll())
            finally:
                process.kill()
                process.wait()

    def test_cleanup_refuses_run_binding_mismatch_before_signalling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            process = subprocess.Popen(["/bin/sleep", "30"])
            try:
                recorded = self.record_handle.record_runtime_handle(
                    authorization("goal-dispatch", "evidence.record"),
                    run_dir,
                    pid=process.pid,
                )
                self.assertTrue(recorded["ok"])
                mismatched = authorization("goal-close", "runtime.cleanup")
                mismatched["goal_id"] = "different-goal"
                mismatched["goal_preflight"]["goal_id"] = "different-goal"
                mismatched["entry_decision"]["entry_session"]["authority_pass"][
                    "cursor"
                ] = {"goal_id": "different-goal"}
                result = self.cleanup.reclaim_runtime_handles(
                    mismatched,
                    run_dir,
                    grace_seconds=0.1,
                )
                self.assertFalse(result["ok"])
                self.assertIn("manifest_goal_id_mismatch", result["errors"])
                self.assertIsNone(process.poll())
                self.assertFalse((run_dir / "cleanup.jsonl").exists())
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()

    def test_goal_sync_requires_ordered_pre_and_post_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            auth = authorization("goal-close", "goal.sync")
            bad_post = self.sync.record_goal_sync(
                auth,
                run_dir,
                phase="post_update",
                goal_status="complete",
                update_called=True,
            )
            self.assertFalse(bad_post["ok"])
            pre = self.sync.record_goal_sync(
                auth,
                run_dir,
                phase="pre_update",
                goal_status="complete",
                update_called=False,
            )
            post = self.sync.record_goal_sync(
                auth,
                run_dir,
                phase="post_update",
                goal_status="complete",
                update_called=True,
            )
            self.assertTrue(pre["ok"])
            self.assertTrue(post["ok"])


if __name__ == "__main__":
    unittest.main()
