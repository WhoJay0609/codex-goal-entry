from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    append_goal_event,
    append_jsonl,
    authorize,
    contains_sensitive_key,
    ensure_goal_event,
    load_json_value,
    load_manifest,
    read_jsonl,
    resolve_external_operation,
    stable_digest,
    utc_now,
    validate_run_binding,
    write_json_atomic,
)


def _ensure_pr_operation_events(
    run_dir: Path, decision: Mapping[str, Any], operation: Mapping[str, Any]
) -> list[str]:
    status = operation.get("status")
    intent_kind = "pr_operation_draft" if status == "draft" else "pr_operation_intent"
    intent = ensure_goal_event(
        run_dir,
        decision,
        kind=intent_kind,
        status="readiness_only",
        data={
            "operation_id": operation.get("operation_id"),
            "desired_state_digest": operation.get("desired_state_digest"),
            "authorized": status != "draft",
        },
        identity_fields=("operation_id", "desired_state_digest"),
    )
    if not intent["ok"]:
        return list(intent["errors"])
    if status != "applied":
        return []
    outcome = ensure_goal_event(
        run_dir,
        decision,
        kind="pr_operation_outcome",
        status="completed",
        data={
            "operation_id": operation.get("operation_id"),
            "provider_id": operation.get("provider_id"),
            "desired_state_digest": operation.get("desired_state_digest"),
        },
        identity_fields=("operation_id", "desired_state_digest"),
    )
    return [] if outcome["ok"] else list(outcome["errors"])


def record_pr_projection(
    request: Mapping[str, Any], run_dir: Path, operation: Mapping[str, Any]
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "errors": decision["reasons"], "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    if request.get("capability") != "goal.sync":
        errors.append("wrong_capability")
    manifest = load_manifest(run_dir)
    operation_id = operation.get("operation_id")
    desired = operation.get("desired_state")
    if not isinstance(operation_id, str) or not operation_id.strip():
        errors.append("pr_operation_id_missing")
    if operation.get("scope_digest") != manifest.get("authorization_scope_digest"):
        errors.append("authorization_scope_digest_mismatch")
    if not isinstance(desired, Mapping) or not desired:
        errors.append("pr_desired_state_missing")
    elif contains_sensitive_key(desired):
        errors.append("pr_desired_state_sensitive")
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}

    desired_state = dict(desired)
    desired_digest = stable_digest(desired_state)
    operations = manifest.setdefault("external_operations", {})
    existing = operations.get(operation_id)
    resolution = resolve_external_operation(
        existing,
        operation.get("provider_result"),
        operation_id=operation_id,
        desired_state_digest=desired_digest,
    )
    if resolution["outcome"] == "error":
        return {
            "ok": False,
            "errors": resolution["errors"],
            "authorization": decision,
        }
    if resolution["outcome"] in {"replayed", "reconcile"}:
        journal_errors = _ensure_pr_operation_events(
            run_dir, decision, resolution["operation"]
        )
        if journal_errors:
            return {
                "ok": False,
                "errors": journal_errors,
                "authorization": decision,
            }
        provider_action = "none"
        if (
            resolution["outcome"] == "reconcile"
            and resolution["operation"].get("status") == "pending"
        ):
            provider_action = "reconcile"
        return {
            "ok": True,
            "operation": resolution["operation"],
            "provider_action": provider_action,
            "replayed": True,
        }
    if resolution["outcome"] == "applied":
        applied = resolution["operation"]
        operations[operation_id] = applied
        manifest["pr_projection"] = dict(applied)
        write_json_atomic(run_dir / "manifest.json", manifest)
        event = append_goal_event(
            run_dir,
            decision,
            kind="pr_operation_outcome",
            status="completed",
            data={
                "operation_id": operation_id,
                "provider_id": applied["provider_id"],
                "desired_state_digest": desired_digest,
            },
        )
        return {"ok": True, "operation": applied, "provider_action": "none", "event": event}
    existing_projection = manifest.get("pr_projection")
    has_provider_identity = (
        isinstance(existing_projection, Mapping)
        and isinstance(existing_projection.get("provider_id"), str)
        and bool(existing_projection.get("provider_id", "").strip())
    )
    if has_provider_identity:
        return {
            "ok": True,
            "operation": dict(existing_projection),
            "provider_action": "none",
            "replayed": True,
        }
    if (
        isinstance(existing_projection, Mapping)
        and existing_projection.get("status") == "pending"
    ):
        return {
            "ok": False,
            "errors": ["pr_projection_reconciliation_required"],
            "authorization": decision,
        }
    authorized = "pr.create" in set(manifest.get("external_actions") or [])
    record = {
        "operation_id": operation_id,
        "desired_state": desired_state,
        "desired_state_digest": desired_digest,
        "scope_digest": operation["scope_digest"],
        "status": "pending" if authorized else "draft",
    }
    operations[operation_id] = record
    manifest["pr_projection"] = dict(record)
    write_json_atomic(run_dir / "manifest.json", manifest)
    event = append_goal_event(
        run_dir,
        decision,
        kind="pr_operation_intent" if authorized else "pr_operation_draft",
        status="readiness_only",
        data={
            "operation_id": operation_id,
            "desired_state_digest": desired_digest,
            "authorized": authorized,
        },
    )
    return {
        "ok": True,
        "operation": record,
        "provider_action": "create" if authorized else "none",
        "event": event,
    }


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
