from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    EVIDENCE_STATUSES,
    append_jsonl,
    authorize,
    load_json_value,
    utc_now,
    validate_run_binding,
)


def record_evidence(
    request: Mapping[str, Any],
    run_dir: Path,
    *,
    kind: str,
    status: str,
    data: Mapping[str, Any],
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "authorization": decision}
    if request.get("capability") != "evidence.record":
        return {"ok": False, "errors": ["wrong_capability"], "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    if status not in EVIDENCE_STATUSES:
        errors.append("evidence_status_invalid")
    if not isinstance(kind, str) or not kind.strip():
        errors.append("evidence_kind_missing")
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}
    row = {
        "event_version": 1,
        "event_id": f"evt-{uuid.uuid4().hex}",
        "timestamp": utc_now(),
        "goal_id": decision["goal_id"],
        "entry_session_id": decision["entry_session_id"],
        "owner_skill": decision["owner_skill"],
        "capability": "evidence.record",
        "kind": kind,
        "status": status,
        "data": dict(data),
    }
    append_jsonl(run_dir / "events.jsonl", row)
    return {"ok": True, "event": row}


def main() -> int:
    parser = argparse.ArgumentParser(description="Append Goal-owned evidence.")
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--data-json", default="{}")
    args = parser.parse_args()
    result = record_evidence(
        load_json_value(args.authorization_json),
        args.run_dir,
        kind=args.kind,
        status=args.status,
        data=load_json_value(args.data_json),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
