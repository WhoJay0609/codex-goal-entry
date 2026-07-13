from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    append_goal_event,
    authorize,
    ensure_goal_event,
    load_json_value,
    load_manifest,
    validate_run_binding,
    write_json_atomic,
)


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references" / "lifecycle-contract.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def record_recovery_action(
    request: Mapping[str, Any],
    run_dir: Path,
    *,
    operation_id: str,
    unit_id: str,
    action: str,
    retry_limit: int,
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "errors": decision["reasons"], "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    if request.get("capability") != "evidence.record":
        errors.append("wrong_capability")
    if action not in {"retry", "replan"}:
        errors.append("recovery_action_invalid")
    if not isinstance(operation_id, str) or not operation_id.strip():
        errors.append("recovery_operation_id_missing")
    if not isinstance(unit_id, str) or not unit_id.strip():
        errors.append("recovery_unit_id_missing")
    max_retries = int(CONTRACT["recovery"]["max_corrective_retries"])
    retry_limit_valid = (
        isinstance(retry_limit, int)
        and not isinstance(retry_limit, bool)
        and 0 <= retry_limit <= max_retries
    )
    if not retry_limit_valid:
        errors.append("retry_limit_invalid")
    manifest = load_manifest(run_dir)
    session = (request.get("entry_decision") or {}).get("entry_session") or {}
    if session.get("authorization_scope_digest") not in {
        None,
        manifest.get("authorization_scope_digest"),
    }:
        errors.append("authorization_scope_digest_mismatch")
    recovery = manifest.setdefault(
        "recovery",
        {
            "retry_counts": {},
            "retry_limits": {},
            "operations": {},
            "replan_count": 0,
        },
    )
    retry_counts = recovery.setdefault("retry_counts", {})
    retry_limits = recovery.setdefault("retry_limits", {})
    operations = recovery.setdefault("operations", {})
    existing_operation = operations.get(operation_id)
    if isinstance(existing_operation, Mapping):
        expected = {
            "operation_id": operation_id,
            "unit_id": unit_id,
            "action": action,
            "retry_limit": retry_limit,
        }
        if any(existing_operation.get(key) != value for key, value in expected.items()):
            errors.append("recovery_operation_conflict")
        if errors:
            return {"ok": False, "errors": errors, "authorization": decision}
        ensured = ensure_goal_event(
            run_dir,
            decision,
            kind="recovery_action",
            status="completed",
            data=dict(existing_operation),
            identity_fields=("operation_id",),
        )
        if not ensured["ok"]:
            return {
                "ok": False,
                "errors": ensured["errors"],
                "authorization": decision,
            }
        return {
            "ok": True,
            "retry_count": existing_operation["retry_count"],
            "retry_limit": existing_operation["retry_limit"],
            "replan_count": existing_operation["replan_count"],
            "event": ensured["event"],
            "replayed": True,
        }
    units = {
        item.get("id"): item
        for item in (manifest.get("task_graph") or {}).get("work_units", [])
        if isinstance(item, Mapping)
    }
    unit = units.get(unit_id)
    if not isinstance(unit, Mapping):
        errors.append("recovery_work_unit_unknown")
    elif unit.get("status") not in {"active", "failed", "blocked"}:
        errors.append("recovery_work_unit_not_retryable")
    current_retry = int(retry_counts.get(unit_id, 0))
    bound_limit = retry_limits.get(unit_id)
    bound_limit_valid = bound_limit is None or (
        isinstance(bound_limit, int)
        and not isinstance(bound_limit, bool)
        and 0 <= bound_limit <= max_retries
    )
    if not bound_limit_valid:
        errors.append("recorded_retry_limit_invalid")
    if bound_limit_valid and bound_limit is not None and bound_limit != retry_limit:
        errors.append("retry_limit_conflict")
    effective_limit = (
        retry_limit
        if retry_limit_valid and bound_limit is None
        else bound_limit
        if bound_limit_valid and bound_limit is not None
        else max_retries
    )
    if action == "retry" and current_retry >= effective_limit:
        errors.append("retry_budget_exhausted")
    if action == "replan":
        if current_retry < effective_limit:
            errors.append("replan_before_retry_exhaustion")
        if int(recovery.get("replan_count", 0)) >= int(
            CONTRACT["recovery"]["automatic_replans"]
        ):
            errors.append("replan_budget_exhausted")
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}

    retry_limits[unit_id] = effective_limit
    if action == "retry":
        retry_counts[unit_id] = current_retry + 1
    else:
        recovery["replan_count"] = int(recovery.get("replan_count", 0)) + 1
    operation_record = {
        "operation_id": operation_id,
        "unit_id": unit_id,
        "action": action,
        "retry_count": int(retry_counts.get(unit_id, 0)),
        "retry_limit": effective_limit,
        "replan_count": int(recovery.get("replan_count", 0)),
    }
    operations[operation_id] = operation_record
    write_json_atomic(run_dir / "manifest.json", manifest)
    event = append_goal_event(
        run_dir,
        decision,
        kind="recovery_action",
        status="completed",
        data=operation_record,
    )
    return {
        "ok": True,
        "retry_count": int(retry_counts.get(unit_id, 0)),
        "retry_limit": effective_limit,
        "replan_count": int(recovery.get("replan_count", 0)),
        "event": event,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Record bounded Goal recovery")
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--action", required=True, choices=["retry", "replan"])
    parser.add_argument("--retry-limit", required=True, type=int)
    args = parser.parse_args()
    result = record_recovery_action(
        load_json_value(args.authorization_json),
        args.run_dir,
        operation_id=args.operation_id,
        unit_id=args.unit_id,
        action=args.action,
        retry_limit=args.retry_limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
