from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    append_jsonl,
    authorize,
    load_json_value,
    process_identity,
    read_jsonl,
    utc_now,
    validate_run_binding,
)


def _wait_for_exit(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if process_identity(pid) is None:
            return True
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    return process_identity(pid) is None


def reclaim_runtime_handles(
    request: Mapping[str, Any], run_dir: Path, *, grace_seconds: float = 2.0
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "authorization": decision}
    if request.get("capability") != "runtime.cleanup":
        return {"ok": False, "errors": ["wrong_capability"], "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    if errors:
        return {
            "ok": False,
            "errors": errors,
            "record": {
                "timestamp": utc_now(),
                "goal_id": decision.get("goal_id"),
                "entry_session_id": decision.get("entry_session_id"),
                "owner_skill": decision.get("owner_skill"),
                "capability": "runtime.cleanup",
                "status": "blocked",
                "outcomes": [],
                "errors": errors,
            },
        }
    handles, parse_errors = read_jsonl(run_dir / "runtime_handles.jsonl")
    errors.extend(parse_errors)
    outcomes = []
    for handle in handles:
        if handle.get("status") not in {None, "active", "running"}:
            continue
        try:
            pid = int(handle["pid"])
        except (KeyError, TypeError, ValueError):
            errors.append("runtime_handle_pid_invalid")
            continue
        expected = (
            str(handle.get("process_start_ticks", "")),
            str(handle.get("command_hash", "")),
        )
        current = process_identity(pid)
        if current is None:
            outcomes.append({"pid": pid, "outcome": "already_exited"})
            continue
        if current != expected:
            errors.append(f"runtime_handle_identity_mismatch:{pid}")
            outcomes.append({"pid": pid, "outcome": "identity_mismatch_refused"})
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            if not _wait_for_exit(pid, grace_seconds):
                os.kill(pid, signal.SIGKILL)
                if not _wait_for_exit(pid, 1.0):
                    raise RuntimeError("process did not exit after SIGKILL")
            outcomes.append({"pid": pid, "outcome": "stopped"})
        except (PermissionError, ProcessLookupError, RuntimeError) as exc:
            errors.append(f"runtime_cleanup_failed:{pid}:{exc}")
            outcomes.append({"pid": pid, "outcome": "failed"})
    record = {
        "timestamp": utc_now(),
        "goal_id": decision.get("goal_id"),
        "entry_session_id": decision.get("entry_session_id"),
        "owner_skill": decision.get("owner_skill"),
        "capability": "runtime.cleanup",
        "status": "failed" if errors else "completed",
        "outcomes": outcomes,
        "errors": errors,
    }
    if not errors or all(not error.startswith("manifest_") for error in errors):
        append_jsonl(run_dir / "cleanup.jsonl", record)
    return {"ok": not errors, "record": record, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reclaim verified run-owned process handles."
    )
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--grace-seconds", type=float, default=2.0)
    args = parser.parse_args()
    result = reclaim_runtime_handles(
        load_json_value(args.authorization_json),
        args.run_dir,
        grace_seconds=args.grace_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
