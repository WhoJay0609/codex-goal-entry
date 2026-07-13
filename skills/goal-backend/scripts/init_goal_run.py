from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    OWNER_CAPABILITIES,
    authorize,
    load_json_value,
    stable_digest,
    utc_now,
    write_json_atomic,
)


def initialize_run(request: Mapping[str, Any], run_dir: Path) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "authorization": decision}
    if request.get("capability") != "run.initialize":
        return {"ok": False, "authorization": decision, "errors": ["wrong_capability"]}
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        same = all(
            existing.get(key) == decision.get(key)
            for key in ("goal_id", "entry_session_id", "request_fingerprint")
        )
        return {
            "ok": same,
            "created": False,
            "run_dir": str(run_dir),
            "errors": [] if same else ["run_binding_conflict"],
        }
    run_dir.mkdir(parents=True, exist_ok=False)
    session = (request.get("entry_decision") or {}).get("entry_session") or {}
    authority = session.get("authority_pass") or {}
    model_route = (request.get("entry_decision") or {}).get("model_route") or {}
    authorization_scope = model_route.get("authorization") or {
        "scope": "legacy goal scope",
        "external_actions": list(authority.get("external_actions") or []),
    }
    scope_digest = session.get("authorization_scope_digest") or stable_digest(
        dict(authorization_scope)
    )
    manifest = {
        "schema": "goal-run/v1",
        "goal_id": decision["goal_id"],
        "entry_session_id": decision["entry_session_id"],
        "request_fingerprint": decision["request_fingerprint"],
        "entry_decision_digest": stable_digest(dict(request["entry_decision"])),
        "goal_preflight_digest": stable_digest(dict(request["goal_preflight"])),
        "initialized_by": decision["owner_skill"],
        "started_at": utc_now(),
        "lifecycle_state": "planning",
        "lifecycle_revision": 0,
        "authorization_scope_digest": scope_digest,
        "external_actions": sorted(authorization_scope.get("external_actions") or []),
        "task_graph": {"version": 1, "milestones": [], "work_units": []},
        "issue_projections": {},
        "external_operations": {},
        "recovery": {
            "retry_counts": {},
            "retry_limits": {},
            "operations": {},
            "replan_count": 0,
        },
        "pr_projection": None,
        "capabilities": sorted(OWNER_CAPABILITIES),
        "evidence_statuses": [
            "completed",
            "missing",
            "partial",
            "failed",
            "blocked",
            "readiness_only",
        ],
    }
    try:
        write_json_atomic(manifest_path, manifest)
    except BaseException:
        try:
            run_dir.rmdir()
        except OSError:
            pass
        raise
    return {"ok": True, "created": True, "run_dir": str(run_dir), "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize a Goal-owned run directory."
    )
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    result = initialize_run(load_json_value(args.authorization_json), args.run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
