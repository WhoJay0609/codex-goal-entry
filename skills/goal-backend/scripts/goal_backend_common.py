from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


EVIDENCE_STATUSES = {
    "completed",
    "missing",
    "partial",
    "failed",
    "blocked",
    "readiness_only",
}

OWNER_CAPABILITIES = {
    "run.initialize": {"goal-context", "goal-dispatch"},
    "evidence.record": {"goal-context", "goal-dispatch", "goal-team"},
    "trace.validate": {"goal-trace", "goal-close"},
    "runtime.cleanup": {"goal-close"},
    "goal.sync": {"goal-close"},
    "trace.read_legacy": {"goal-trace"},
}

SESSION_ID_RE = re.compile(r"^entry-[a-z0-9]{12,64}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
EXTERNAL_ACTIONS = {"issue.create", "issue.update", "pr.create"}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json_value(value: str | Path | Mapping[str, Any]) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raw = str(value)
    if raw.lstrip().startswith("{"):
        loaded = json.loads(raw)
    else:
        loaded = json.loads(Path(raw).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("expected a JSON object")
    return loaded


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    if not path.exists():
        return rows, errors
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name}:{line_number}: expected object")
            continue
        rows.append(value)
    return rows, errors


def stable_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_manifest(run_dir: Path) -> Dict[str, Any]:
    value = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    return value


def append_goal_event(
    run_dir: Path,
    decision: Mapping[str, Any],
    *,
    kind: str,
    status: str,
    data: Mapping[str, Any],
) -> Dict[str, Any]:
    row = {
        "event_version": 1,
        "event_id": f"evt-{uuid.uuid4().hex}",
        "timestamp": utc_now(),
        "goal_id": decision["goal_id"],
        "entry_session_id": decision["entry_session_id"],
        "owner_skill": decision["owner_skill"],
        "capability": decision["capability"],
        "kind": kind,
        "status": status,
        "data": dict(data),
    }
    append_jsonl(run_dir / "events.jsonl", row)
    return row


def ensure_goal_event(
    run_dir: Path,
    decision: Mapping[str, Any],
    *,
    kind: str,
    status: str,
    data: Mapping[str, Any],
    identity_fields: Tuple[str, ...],
) -> Dict[str, Any]:
    rows, errors = read_jsonl(run_dir / "events.jsonl")
    if errors:
        return {"ok": False, "errors": errors}
    expected = dict(data)
    for row in rows:
        row_data = row.get("data") or {}
        if row.get("kind") == kind and all(
            row_data.get(field) == expected.get(field) for field in identity_fields
        ):
            if row.get("status") != status:
                return {"ok": False, "errors": ["goal_event_status_conflict"]}
            return {"ok": True, "created": False, "event": row}
    event = append_goal_event(
        run_dir, decision, kind=kind, status=status, data=expected
    )
    return {"ok": True, "created": True, "event": event}


SENSITIVE_KEYS = {
    "api_key",
    "api_token",
    "access_token",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}


def contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS or contains_sensitive_key(item):
                return True
    elif isinstance(value, list):
        return any(contains_sensitive_key(item) for item in value)
    return False


def validate_provider_result(
    value: Mapping[str, Any], *, operation_id: str, desired_state_digest: str
) -> List[str]:
    allowed = {
        "operation_id",
        "desired_state_digest",
        "provider_id",
        "url",
        "state",
    }
    errors: List[str] = []
    if set(value) - allowed or contains_sensitive_key(value):
        errors.append("provider_result_fields_invalid")
    if value.get("operation_id") != operation_id:
        errors.append("provider_result_operation_mismatch")
    if value.get("desired_state_digest") != desired_state_digest:
        errors.append("provider_result_digest_mismatch")
    if not isinstance(value.get("provider_id"), str) or not str(
        value.get("provider_id", "")
    ).strip():
        errors.append("provider_result_id_missing")
    url = value.get("url")
    if url is not None and (not isinstance(url, str) or not url.startswith("https://")):
        errors.append("provider_result_url_invalid")
    state = value.get("state")
    if state is not None and (
        not isinstance(state, str) or not state.strip()
    ):
        errors.append("provider_result_state_invalid")
    return errors


def resolve_external_operation(
    existing: Any,
    provider_result: Any,
    *,
    operation_id: str,
    desired_state_digest: str,
) -> Dict[str, Any]:
    if not isinstance(existing, Mapping):
        if provider_result is not None:
            return {
                "outcome": "error",
                "errors": ["provider_result_without_recorded_intent"],
            }
        return {"outcome": "new"}
    if existing.get("desired_state_digest") != desired_state_digest:
        return {
            "outcome": "error",
            "errors": ["external_operation_digest_conflict"],
        }
    if existing.get("status") == "applied":
        return {"outcome": "replayed", "operation": dict(existing)}
    if provider_result is not None and not isinstance(provider_result, Mapping):
        return {"outcome": "error", "errors": ["provider_result_invalid"]}
    if isinstance(provider_result, Mapping) and existing.get("status") != "pending":
        return {
            "outcome": "error",
            "errors": ["provider_result_for_unauthorized_draft"],
        }
    if provider_result is None:
        return {"outcome": "reconcile", "operation": dict(existing)}
    errors = validate_provider_result(
        provider_result,
        operation_id=operation_id,
        desired_state_digest=desired_state_digest,
    )
    if errors:
        return {"outcome": "error", "errors": errors}
    applied = dict(existing)
    applied.update(
        {
            "status": "applied",
            "provider_id": provider_result["provider_id"],
            "url": provider_result.get("url"),
            "provider_state": provider_result.get("state"),
        }
    )
    return {"outcome": "applied", "operation": applied}


def process_identity(pid: int) -> Tuple[str, str] | None:
    root = Path("/proc") / str(pid)
    try:
        stat_text = (root / "stat").read_text(encoding="utf-8")
        _, remainder = stat_text.rsplit(") ", 1)
        fields = remainder.split()
        if fields[0] == "Z":
            return None
        start_ticks = fields[19]
        command_hash = hashlib.sha256((root / "cmdline").read_bytes()).hexdigest()
    except (
        FileNotFoundError,
        IndexError,
        PermissionError,
        ProcessLookupError,
        ValueError,
    ):
        return None
    return start_ticks, command_hash


def authorize(request: Mapping[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    actor = request.get("actor")
    owner = request.get("owner_skill")
    capability = request.get("capability")
    operation_phase = request.get("operation_phase", "active")
    goal_id = request.get("goal_id")
    decision = request.get("entry_decision")
    preflight = request.get("goal_preflight")

    if actor != "main_orchestrator":
        reasons.append("actor_not_main_orchestrator")
    if capability not in OWNER_CAPABILITIES:
        reasons.append("capability_unknown")
    elif owner not in OWNER_CAPABILITIES[capability]:
        reasons.append("owner_not_authorized_for_capability")
    if operation_phase not in {"planning", "active", "verifying", "closeout", "legacy_read"}:
        reasons.append("operation_phase_invalid")
    if not isinstance(decision, Mapping):
        reasons.append("entry_decision_missing")
        decision = {}
    if decision.get("execution_destination") != "goal_lifecycle":
        reasons.append("entry_route_not_goal_lifecycle")
    session = decision.get("entry_session")
    if not isinstance(session, Mapping):
        reasons.append("entry_session_missing")
        session = {}
    session_id = session.get("session_id")
    if not isinstance(session_id, str) or not SESSION_ID_RE.fullmatch(session_id):
        reasons.append("entry_session_id_invalid")
    if session.get("status") not in {"in_progress", "complete"}:
        reasons.append("entry_session_state_invalid")
    semantic = session.get("semantic_pass")
    if not isinstance(semantic, Mapping) or semantic.get("status") != "resolved":
        reasons.append("semantic_pass_not_resolved")
    authority = session.get("authority_pass")
    if not isinstance(authority, Mapping):
        reasons.append("authority_pass_missing")
        authority = {}
    model_route = decision.get("model_route")
    if model_route is not None:
        if not isinstance(model_route, Mapping):
            reasons.append("model_route_invalid")
        else:
            authorization_scope = model_route.get("authorization")
            if not isinstance(authorization_scope, Mapping):
                reasons.append("model_route_authorization_missing")
            else:
                scope = authorization_scope.get("scope")
                actions = authorization_scope.get("external_actions")
                actions_valid = (
                    isinstance(actions, list)
                    and all(
                        isinstance(action, str) and action in EXTERNAL_ACTIONS
                        for action in actions
                    )
                    and len(actions) == len(set(actions))
                )
                if not isinstance(scope, str) or not scope.strip():
                    reasons.append("model_route_authorization_scope_invalid")
                if not actions_valid:
                    reasons.append("model_route_external_actions_invalid")
                if isinstance(scope, str) and scope.strip() and actions_valid:
                    normalized_scope = {
                        "scope": scope.strip(),
                        "external_actions": sorted(actions),
                    }
                    if session.get("authorization_scope_digest") != stable_digest(
                        normalized_scope
                    ):
                        reasons.append("authorization_scope_digest_mismatch")
                    authority_actions = authority.get("external_actions")
                    if (
                        not isinstance(authority_actions, list)
                        or any(
                            not isinstance(action, str)
                            for action in authority_actions
                        )
                        or sorted(authority_actions) != normalized_scope["external_actions"]
                    ):
                        reasons.append("authority_external_actions_mismatch")
            if model_route.get("goal_action") == "resume":
                route_cursor = model_route.get("resume_cursor")
                authority_cursor = authority.get("cursor")
                if (
                    not isinstance(route_cursor, Mapping)
                    or not isinstance(authority_cursor, Mapping)
                    or dict(authority_cursor) != dict(route_cursor)
                ):
                    reasons.append("authority_resume_cursor_mismatch")
    if authority.get("status") == "blocked":
        reasons.append("authority_pass_blocked")
    planning_operation = capability == "run.initialize" or (
        capability == "evidence.record" and operation_phase == "planning"
    )
    legacy_read = capability == "trace.read_legacy"
    if planning_operation:
        if authority.get("planning_mutation_allowed") is not True:
            reasons.append("planning_mutation_not_allowed")
    elif not legacy_read and authority.get("phase_execution_allowed") is not True:
        reasons.append("phase_execution_not_allowed")
    fingerprint = decision.get("request_fingerprint") or session.get(
        "request_fingerprint"
    )
    if not isinstance(fingerprint, str) or not FINGERPRINT_RE.fullmatch(fingerprint):
        reasons.append("request_fingerprint_invalid")
    session_fingerprint = session.get("request_fingerprint")
    if session_fingerprint is not None and session_fingerprint != fingerprint:
        reasons.append("session_fingerprint_mismatch")
    if not isinstance(preflight, Mapping):
        reasons.append("goal_preflight_missing")
        preflight = {}
    if preflight.get("ready") is not True:
        reasons.append("goal_preflight_not_ready")
    if preflight.get("entry_session_id") != session_id:
        reasons.append("preflight_session_mismatch")
    if preflight.get("request_fingerprint") != fingerprint:
        reasons.append("preflight_fingerprint_mismatch")
    if not isinstance(goal_id, str) or not goal_id.strip():
        reasons.append("goal_id_missing")
    if preflight.get("goal_id") not in {None, goal_id}:
        reasons.append("preflight_goal_mismatch")
    cursor = authority.get("cursor")
    if isinstance(cursor, Mapping) and cursor.get("goal_id") not in {None, goal_id}:
        reasons.append("cursor_goal_mismatch")

    return {
        "allowed": not reasons,
        "reasons": reasons,
        "actor": actor,
        "owner_skill": owner,
        "capability": capability,
        "operation_phase": operation_phase,
        "goal_id": goal_id,
        "entry_session_id": session_id,
        "request_fingerprint": fingerprint,
        "checked_at": utc_now(),
        "boundary": "goal_protocol_not_os_sandbox",
    }


def validate_run_binding(run_dir: Path, decision: Mapping[str, Any]) -> List[str]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest_missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["manifest_invalid"]
    errors: List[str] = []
    for key, decision_key in (
        ("goal_id", "goal_id"),
        ("entry_session_id", "entry_session_id"),
        ("request_fingerprint", "request_fingerprint"),
    ):
        if manifest.get(key) != decision.get(decision_key):
            errors.append(f"manifest_{key}_mismatch")
    return errors


def status_from_rows(rows: Iterable[Mapping[str, Any]]) -> str:
    statuses = [row.get("status") for row in rows]
    if not statuses:
        return "missing"
    for status in ("failed", "blocked", "partial", "missing", "readiness_only"):
        if status in statuses:
            return status
    return "completed"
