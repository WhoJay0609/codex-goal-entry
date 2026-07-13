from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    append_jsonl,
    authorize,
    load_json_value,
    process_identity,
    utc_now,
    validate_run_binding,
)


def record_runtime_handle(
    request: Mapping[str, Any], run_dir: Path, *, pid: int
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    if request.get("capability") != "evidence.record":
        errors.append("wrong_capability")
    identity = process_identity(pid)
    if identity is None:
        errors.append("process_not_running")
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}
    start_ticks, command_hash = identity
    record = {
        "timestamp": utc_now(),
        "goal_id": decision["goal_id"],
        "entry_session_id": decision["entry_session_id"],
        "owner_skill": decision["owner_skill"],
        "capability": "evidence.record",
        "kind": "runtime_handle",
        "pid": pid,
        "process_start_ticks": start_ticks,
        "command_hash": command_hash,
        "status": "active",
    }
    append_jsonl(run_dir / "runtime_handles.jsonl", record)
    return {"ok": True, "record": record}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record one verified run-owned process handle."
    )
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--pid", required=True, type=int)
    args = parser.parse_args()
    result = record_runtime_handle(
        load_json_value(args.authorization_json), args.run_dir, pid=args.pid
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
