from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    append_jsonl,
    authorize,
    load_json_value,
    read_jsonl,
    utc_now,
    validate_run_binding,
)


def record_goal_sync(
    request: Mapping[str, Any],
    run_dir: Path,
    *,
    phase: str,
    goal_status: str,
    update_called: bool,
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    if request.get("capability") != "goal.sync":
        errors.append("wrong_capability")
    if phase not in {"pre_update", "post_update"}:
        errors.append("goal_sync_phase_invalid")
    if goal_status not in {"complete", "blocked"}:
        errors.append("goal_status_invalid")
    rows, parse_errors = read_jsonl(run_dir / "goal_sync.jsonl")
    errors.extend(parse_errors)
    if phase == "pre_update" and update_called:
        errors.append("pre_update_cannot_claim_update_called")
    if phase == "post_update":
        if not update_called:
            errors.append("post_update_requires_update_called")
        if not any(
            row.get("phase") == "pre_update" and row.get("goal_status") == goal_status
            for row in rows
        ):
            errors.append("matching_pre_update_missing")
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}
    record = {
        "timestamp": utc_now(),
        "goal_id": decision["goal_id"],
        "entry_session_id": decision["entry_session_id"],
        "owner_skill": decision["owner_skill"],
        "capability": "goal.sync",
        "phase": phase,
        "goal_status": goal_status,
        "update_called": update_called,
    }
    append_jsonl(run_dir / "goal_sync.jsonl", record)
    return {"ok": True, "record": record}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record ordered Goal status synchronization evidence."
    )
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--phase", choices=["pre_update", "post_update"], required=True)
    parser.add_argument("--goal-status", choices=["complete", "blocked"], required=True)
    parser.add_argument("--update-called", action="store_true")
    args = parser.parse_args()
    result = record_goal_sync(
        load_json_value(args.authorization_json),
        args.run_dir,
        phase=args.phase,
        goal_status=args.goal_status,
        update_called=args.update_called,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
