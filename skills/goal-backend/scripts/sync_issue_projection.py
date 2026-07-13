from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    append_goal_event,
    authorize,
    contains_sensitive_key,
    ensure_goal_event,
    load_json_value,
    load_manifest,
    resolve_external_operation,
    stable_digest,
    validate_run_binding,
    write_json_atomic,
)


def _ensure_operation_events(
    run_dir: Path, decision: Mapping[str, Any], operation: Mapping[str, Any]
) -> list[str]:
    status = operation.get("status")
    intent_kind = (
        "issue_operation_draft" if status == "draft" else "issue_operation_intent"
    )
    intent = ensure_goal_event(
        run_dir,
        decision,
        kind=intent_kind,
        status="readiness_only",
        data={
            "operation_id": operation.get("operation_id"),
            "mapping_key": operation.get("mapping_key"),
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
        kind="issue_operation_outcome",
        status="completed",
        data={
            "operation_id": operation.get("operation_id"),
            "mapping_key": operation.get("mapping_key"),
            "provider_id": operation.get("provider_id"),
            "desired_state_digest": operation.get("desired_state_digest"),
        },
        identity_fields=("operation_id", "desired_state_digest"),
    )
    return [] if outcome["ok"] else list(outcome["errors"])


def _operation_errors(manifest: Mapping[str, Any], operation: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("operation_id", "mapping_key", "milestone_id", "issue_kind", "action"):
        if not isinstance(operation.get(field), str) or not str(operation.get(field)).strip():
            errors.append(f"issue_operation_{field}_missing")
    if operation.get("action") not in {"create", "update"}:
        errors.append("issue_operation_action_invalid")
    if operation.get("issue_kind") not in {"primary", "child"}:
        errors.append("issue_kind_invalid")
    if (
        operation.get("issue_kind") == "primary"
        and operation.get("mapping_key")
        != f"milestone:{operation.get('milestone_id')}"
    ):
        errors.append("primary_issue_mapping_invalid")
    if operation.get("scope_digest") != manifest.get("authorization_scope_digest"):
        errors.append("authorization_scope_digest_mismatch")
    desired = operation.get("desired_state")
    if not isinstance(desired, Mapping) or not desired:
        errors.append("issue_desired_state_missing")
    elif contains_sensitive_key(desired):
        errors.append("issue_desired_state_sensitive")
    if operation.get("issue_kind") == "child":
        qualification = operation.get("qualification")
        if not isinstance(qualification, Mapping) or not any(
            qualification.get(key) is True
            for key in ("independently_deliverable", "independently_accepted", "blocking")
        ):
            errors.append("child_issue_not_independently_qualifying")
    return errors


def sync_issue_projection(
    request: Mapping[str, Any], run_dir: Path, operation: Mapping[str, Any]
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "errors": decision["reasons"], "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    if request.get("capability") != "evidence.record":
        errors.append("wrong_capability")
    manifest = load_manifest(run_dir)
    errors.extend(_operation_errors(manifest, operation))
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}

    operation_id = str(operation["operation_id"])
    mapping_key = str(operation["mapping_key"])
    desired = dict(operation["desired_state"])
    desired_digest = stable_digest(desired)
    external_operations = manifest.setdefault("external_operations", {})
    projections = manifest.setdefault("issue_projections", {})
    existing_operation = external_operations.get(operation_id)
    existing_projection = projections.get(mapping_key)

    resolution = resolve_external_operation(
        existing_operation,
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
        journal_errors = _ensure_operation_events(
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
        target_provider_id = applied.get("target_provider_id")
        if target_provider_id and applied.get("provider_id") != target_provider_id:
            return {
                "ok": False,
                "errors": ["issue_update_provider_identity_mismatch"],
                "authorization": decision,
            }
        external_operations[operation_id] = applied
        projections[mapping_key] = dict(applied)
        write_json_atomic(run_dir / "manifest.json", manifest)
        event = append_goal_event(
            run_dir,
            decision,
            kind="issue_operation_outcome",
            status="completed",
            data={
                "operation_id": operation_id,
                "mapping_key": mapping_key,
                "provider_id": applied["provider_id"],
                "desired_state_digest": desired_digest,
            },
        )
        return {"ok": True, "operation": applied, "provider_action": "none", "event": event}
    update_target: Mapping[str, Any] | None = None
    has_provider_identity = (
        isinstance(existing_projection, Mapping)
        and isinstance(existing_projection.get("provider_id"), str)
        and bool(existing_projection.get("provider_id", "").strip())
    )
    if has_provider_identity:
        if operation["action"] == "create":
            return {
                "ok": True,
                "operation": dict(existing_projection),
                "provider_action": "none",
                "replayed": True,
            }
        if existing_projection.get("status") == "pending":
            return {
                "ok": False,
                "errors": ["issue_projection_reconciliation_required"],
                "authorization": decision,
            }
        if (
            existing_projection.get("milestone_id") != operation["milestone_id"]
            or existing_projection.get("issue_kind") != operation["issue_kind"]
        ):
            return {
                "ok": False,
                "errors": ["issue_projection_identity_conflict"],
                "authorization": decision,
            }
        update_target = existing_projection
    elif operation["action"] == "update":
        return {
            "ok": False,
            "errors": ["issue_update_target_missing"],
            "authorization": decision,
        }

    required_grant = "issue.create" if operation["action"] == "create" else "issue.update"
    authorized = required_grant in set(manifest.get("external_actions") or [])
    record = {
        "operation_id": operation_id,
        "mapping_key": mapping_key,
        "milestone_id": operation["milestone_id"],
        "issue_kind": operation["issue_kind"],
        "action": operation["action"],
        "desired_state": desired,
        "desired_state_digest": desired_digest,
        "scope_digest": operation["scope_digest"],
        "status": "pending" if authorized else "draft",
    }
    if update_target is not None:
        record["target_provider_id"] = update_target["provider_id"]
        record["provider_id"] = update_target["provider_id"]
        record["url"] = update_target.get("url")
        record["provider_state"] = update_target.get("provider_state")
    external_operations[operation_id] = record
    projections[mapping_key] = dict(record)
    write_json_atomic(run_dir / "manifest.json", manifest)
    event = append_goal_event(
        run_dir,
        decision,
        kind="issue_operation_intent" if authorized else "issue_operation_draft",
        status="readiness_only",
        data={
            "operation_id": operation_id,
            "mapping_key": mapping_key,
            "desired_state_digest": desired_digest,
            "authorized": authorized,
        },
    )
    return {
        "ok": True,
        "operation": record,
        "provider_action": operation["action"] if authorized else "none",
        "event": event,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize one Issue projection")
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--operation-json", required=True)
    args = parser.parse_args()
    result = sync_issue_projection(
        load_json_value(args.authorization_json),
        args.run_dir,
        load_json_value(args.operation_json),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
