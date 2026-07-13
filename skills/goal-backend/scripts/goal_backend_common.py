from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
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
    goal_id = request.get("goal_id")
    decision = request.get("entry_decision")
    preflight = request.get("goal_preflight")

    if actor != "main_orchestrator":
        reasons.append("actor_not_main_orchestrator")
    if capability not in OWNER_CAPABILITIES:
        reasons.append("capability_unknown")
    elif owner not in OWNER_CAPABILITIES[capability]:
        reasons.append("owner_not_authorized_for_capability")
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
    if authority.get("status") == "blocked":
        reasons.append("authority_pass_blocked")
    if authority.get("phase_execution_allowed") is not True:
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
