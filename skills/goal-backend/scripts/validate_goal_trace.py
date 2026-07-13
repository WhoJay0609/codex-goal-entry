from __future__ import annotations

import argparse
import json
from pathlib import Path

from goal_backend_common import (
    EVIDENCE_STATUSES,
    authorize,
    load_json_value,
    read_jsonl,
    status_from_rows,
    validate_run_binding,
)


GOVERNED_CLAIMS = {"code", "experiment", "release", "security"}


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
    rows, row_errors = read_jsonl(run_dir / "events.jsonl")
    errors.extend(row_errors)
    for index, row in enumerate(rows, 1):
        if row.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"events.jsonl:{index}: invalid evidence status")
        if row.get("goal_id") != manifest.get("goal_id"):
            errors.append(f"events.jsonl:{index}: goal mismatch")
        if row.get("entry_session_id") != manifest.get("entry_session_id"):
            errors.append(f"events.jsonl:{index}: session mismatch")
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
