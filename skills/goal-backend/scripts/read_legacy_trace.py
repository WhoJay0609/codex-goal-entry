from __future__ import annotations

import argparse
import json
from pathlib import Path

from goal_backend_common import authorize, load_json_value, read_jsonl


def read_legacy_trace(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return {
            "valid": False,
            "status": "invalid",
            "replay_supported": False,
            "errors": ["manifest_missing"],
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "valid": False,
            "status": "invalid",
            "replay_supported": False,
            "errors": [f"manifest_invalid:{exc}"],
        }
    if not isinstance(manifest.get("schema_version"), int) or not manifest.get(
        "run_id"
    ):
        return {
            "valid": False,
            "status": "invalid",
            "replay_supported": False,
            "errors": ["legacy_manifest_unrecognized"],
        }
    events_path = run_dir / "events.jsonl"
    if not events_path.is_file():
        return {
            "valid": True,
            "status": "partial",
            "legacy_schema_version": manifest["schema_version"],
            "run_id": manifest["run_id"],
            "replay_supported": False,
            "errors": ["events_missing"],
        }
    rows, errors = read_jsonl(events_path)
    calls = {
        row.get("tool_call_id") for row in rows if row.get("event_type") == "tool_call"
    }
    observations = {
        row.get("tool_call_id")
        for row in rows
        if row.get("event_type") == "tool_observation"
    }
    missing = sorted(item for item in calls - observations if item)
    if missing:
        errors.append("tool_calls_without_observation:" + ",".join(missing))
    return {
        "valid": not errors,
        "status": "invalid" if errors else "supported",
        "legacy_schema_version": manifest["schema_version"],
        "run_id": manifest["run_id"],
        "termination_status": (manifest.get("termination") or {}).get("status"),
        "event_count": len(rows),
        "replay_supported": False,
        "errors": errors,
        "ignored_legacy_authority_fields": [
            key
            for key in ("mode", "team_policy", "provider", "auto_state")
            if key in manifest
        ],
    }


def read_legacy_authorized(request: dict, run_dir: Path) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {
            "valid": False,
            "status": "blocked",
            "replay_supported": False,
            "errors": decision["reasons"],
            "authorization": decision,
        }
    if request.get("capability") != "trace.read_legacy":
        return {
            "valid": False,
            "status": "blocked",
            "replay_supported": False,
            "errors": ["wrong_capability"],
            "authorization": decision,
        }
    return read_legacy_trace(run_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read a legacy harness trace without executing it."
    )
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    result = read_legacy_authorized(
        load_json_value(args.authorization_json), args.run_dir
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
