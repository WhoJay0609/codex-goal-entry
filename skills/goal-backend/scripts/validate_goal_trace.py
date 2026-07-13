from __future__ import annotations

import argparse
import json
from pathlib import Path

from goal_backend_common import (
    EVIDENCE_STATUSES,
    OWNER_CAPABILITIES,
    authorize,
    load_json_value,
    read_jsonl,
    status_from_rows,
    validate_run_binding,
)


GOVERNED_CLAIMS = {"code", "experiment", "release", "security"}
EXTERNAL_INTENT_KINDS = {
    "issue_operation_intent",
    "issue_operation_draft",
    "pr_operation_intent",
    "pr_operation_draft",
}
EXTERNAL_OUTCOME_KINDS = {"issue_operation_outcome", "pr_operation_outcome"}


def validate_run(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return {"valid": False, "status": "missing", "errors": ["manifest_missing"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "valid": False,
            "status": "failed",
            "errors": [f"manifest_invalid:{exc}"],
        }
    if manifest.get("schema") != "goal-run/v1":
        return {
            "valid": False,
            "status": "blocked",
            "errors": ["legacy_trace_requires_trace.read_legacy"],
        }
    errors = []
    for field in ("goal_id", "entry_session_id", "request_fingerprint"):
        if not manifest.get(field):
            errors.append(f"manifest_{field}_missing")
    if manifest.get("lifecycle_state") not in {
        "planning",
        "active",
        "verifying",
        "completed",
        "blocked",
    }:
        errors.append("manifest_lifecycle_state_invalid")
    if not isinstance(manifest.get("lifecycle_revision"), int) or manifest.get(
        "lifecycle_revision", -1
    ) < 0:
        errors.append("manifest_lifecycle_revision_invalid")
    scope_digest = manifest.get("authorization_scope_digest")
    if not isinstance(scope_digest, str) or len(scope_digest) != 64:
        errors.append("manifest_authorization_scope_digest_invalid")
    rows, row_errors = read_jsonl(run_dir / "events.jsonl")
    errors.extend(row_errors)
    event_ids = set()
    for index, row in enumerate(rows, 1):
        if row.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"events.jsonl:{index}: invalid evidence status")
        if row.get("goal_id") != manifest.get("goal_id"):
            errors.append(f"events.jsonl:{index}: goal mismatch")
        if row.get("entry_session_id") != manifest.get("entry_session_id"):
            errors.append(f"events.jsonl:{index}: session mismatch")
        if row.get("capability") not in OWNER_CAPABILITIES:
            errors.append(f"events.jsonl:{index}: capability invalid")
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            errors.append(f"events.jsonl:{index}: event id missing")
        elif event_id in event_ids:
            errors.append(f"events.jsonl:{index}: duplicate event id")
        event_ids.add(event_id)
    lifecycle_rows = [row for row in rows if row.get("kind") == "lifecycle_transition"]
    if lifecycle_rows:
        revisions = [(row.get("data") or {}).get("revision") for row in lifecycle_rows]
        if revisions != list(range(1, len(revisions) + 1)):
            errors.append("lifecycle_event_revision_sequence_invalid")
        if revisions[-1] != manifest.get("lifecycle_revision"):
            errors.append("lifecycle_manifest_revision_mismatch")
        if (lifecycle_rows[-1].get("data") or {}).get("to") != manifest.get(
            "lifecycle_state"
        ):
            errors.append("lifecycle_manifest_state_mismatch")
    elif manifest.get("lifecycle_revision") != 0:
        errors.append("lifecycle_transition_event_missing")

    intent_operation_ids = {
        (row.get("data") or {}).get("operation_id")
        for row in rows
        if row.get("kind") in EXTERNAL_INTENT_KINDS
    }
    outcome_operation_ids = {
        (row.get("data") or {}).get("operation_id")
        for row in rows
        if row.get("kind") in EXTERNAL_OUTCOME_KINDS
    }
    operations = manifest.get("external_operations") or {}
    for operation_id, operation in operations.items():
        if not isinstance(operation, dict):
            errors.append(f"external_operation_invalid:{operation_id}")
            continue
        status = operation.get("status")
        if status not in {"draft", "pending", "applied"}:
            errors.append(f"external_operation_status_invalid:{operation_id}")
        if operation_id not in intent_operation_ids:
            errors.append(f"external_operation_intent_missing:{operation_id}")
        if status == "applied" and operation_id not in outcome_operation_ids:
            errors.append(f"external_operation_outcome_missing:{operation_id}")
        if status != "applied" and operation_id in outcome_operation_ids:
            errors.append(f"external_operation_outcome_without_apply:{operation_id}")
    acceptance_rows = [
        row for row in rows if row.get("kind") == "independent_acceptance"
    ]
    if rows:
        from check_independent_acceptance import check_acceptance

        for claim in (row for row in rows if row.get("kind") == "claim"):
            data = claim.get("data") or {}
            claim_type = data.get("claim_type")
            claim_id = data.get("claim_id")
            if claim_type not in GOVERNED_CLAIMS:
                continue
            if not isinstance(claim_id, str) or not claim_id.strip():
                errors.append("governed_claim_id_missing")
                continue
            candidates = [
                row
                for row in acceptance_rows
                if (row.get("data") or {}).get("claim_id") == claim_id
                and row.get("status") == "completed"
            ]
            accepted = False
            for candidate in candidates:
                acceptance = candidate.get("data") or {}
                verdict = check_acceptance(
                    claim_type=str(claim_type),
                    executor_id=str(data.get("executor_id", "")),
                    verifier_id=str(acceptance.get("verifier_id", "")),
                    verifier_expert=str(acceptance.get("verifier_expert", "")),
                    accepted=acceptance.get("accepted") is True,
                )
                if verdict["accepted"]:
                    accepted = True
                    break
            if not accepted:
                errors.append(
                    f"independent_acceptance_missing:{claim_id or '<missing-claim-id>'}"
                )
    return {
        "valid": not errors,
        "status": "failed" if errors else status_from_rows(rows),
        "schema": "goal-run/v1",
        "event_count": len(rows),
        "errors": errors,
    }


def validate_authorized(request: dict, run_dir: Path) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {
            "valid": False,
            "status": "blocked",
            "errors": decision["reasons"],
            "authorization": decision,
        }
    if request.get("capability") != "trace.validate":
        return {
            "valid": False,
            "status": "blocked",
            "errors": ["wrong_capability"],
            "authorization": decision,
        }
    binding_errors = validate_run_binding(run_dir, decision)
    if binding_errors:
        return {
            "valid": False,
            "status": "blocked",
            "errors": binding_errors,
            "authorization": decision,
        }
    return validate_run(run_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Goal or legacy trace evidence."
    )
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    result = validate_authorized(load_json_value(args.authorization_json), args.run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
