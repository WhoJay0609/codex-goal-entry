#!/usr/bin/env python3
"""Bind a model-owned Goal route to the lightweight Goal preflight contract."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


SCHEMA = "goal-preflight.preflight.v2"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
FAMILY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = FAMILY_ROOT.parent
GOAL_ENTRY_ROOT = (
    SOURCE_ROOT
    if (SOURCE_ROOT / "references" / "model_route_contract.json").is_file()
    else FAMILY_ROOT / "goal-entry"
)
MODEL_ROUTE_VALIDATOR = GOAL_ENTRY_ROOT / "scripts" / "validate_model_route.py"
LEGACY_GOAL_ENTRY_RESOLVER = GOAL_ENTRY_ROOT / "scripts" / "resolve_goal_entry.py"
GOAL_CONTEXT_RESOLVER = (
    FAMILY_ROOT / "goal-context" / "scripts" / "ensure_agents_context.py"
)


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def read_text_arg(value: str | None, file_value: str | None) -> str:
    if value and file_value:
        raise SystemExit("pass either inline text or a file path, not both")
    if file_value:
        return Path(file_value).read_text(encoding="utf-8")
    return value or ""


def load_json_arg(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    if value.lstrip().startswith("{"):
        loaded = json.loads(value)
    else:
        loaded = json.loads(Path(value).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("expected a JSON object")
    return loaded


def stable_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_legacy_decision(args: argparse.Namespace, objective_text: str) -> dict[str, Any]:
    resolver = load_module(
        LEGACY_GOAL_ENTRY_RESOLVER, "goal_entry_preflight_legacy_resolver"
    )
    return resolver.resolve(
        SimpleNamespace(
            request=args.request,
            request_file=args.request_file,
            objective=objective_text,
            objective_file=None,
            conversation_mode=args.conversation_mode,
            active_goal_json=args.active_goal_json,
            runtime_state_json=None,
            capabilities_json=None,
            readiness_status=args.readiness_status,
        )
    )


def build_model_decision(
    route_value: str, existing_session_value: str | None = None
) -> tuple[dict[str, Any], list[str], str]:
    validator = load_module(MODEL_ROUTE_VALIDATOR, "goal_entry_model_route_validator")
    validated = validator.validate_model_route(route_value)
    if not validated["ok"]:
        return {}, [f"model_route_invalid:{item}" for item in validated["errors"]], "new"

    route = validated["route"]
    if route["execution_level"] != "goal":
        return {
            "schema": "goal-entry.decision.v3",
            "execution_destination": {
                "direct": "direct",
                "compound": "compound_engineering",
                "none": None,
            }[route["execution_level"]],
            "model_route": route,
        }, ["entry_route_not_goal_lifecycle"], "new"

    inherited = route.get("inherited_context") or {}
    task_instruction = (
        inherited.get("authoritative_instruction")
        if route.get("route_source") == "inherited_context"
        else route["authoritative_instruction"]
    )
    fingerprint_payload = {
        "authoritative_instruction": task_instruction,
        "objective": route["objective"],
        "execution_level": route["execution_level"],
        "intent": route["intent"],
        "goal_action": route["goal_action"],
        "preferred_skill": route.get("preferred_skill"),
        "authorization": route["authorization"],
        "resume_cursor": route.get("resume_cursor"),
    }
    fingerprint = stable_digest(fingerprint_payload)
    identity_source = str(route.get("idempotency_key") or fingerprint)
    session_id = "entry-" + hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:24]
    scope_digest = stable_digest(dict(route["authorization"]))
    cursor = route.get("resume_cursor")
    session = {
        "version": 3,
        "session_id": session_id,
        "status": "in_progress",
        "lifecycle_state": "planning",
        "request_fingerprint": fingerprint,
        "idempotency_key": route.get("idempotency_key"),
        "authorization_scope_digest": scope_digest,
        "semantic_pass": {"status": "resolved", "source": "model_route"},
        "authority_pass": {
            "status": "planning_only",
            "goal_mutation_allowed": True,
            "planning_mutation_allowed": True,
            "phase_execution_allowed": False,
            "external_actions": route["authorization"]["external_actions"],
            "cursor": cursor,
        },
    }
    blockers: list[str] = []
    outcome = "new"
    try:
        existing = load_json_arg(existing_session_value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        existing = None
        blockers.append(f"existing_session_invalid:{exc}")
    if existing is not None:
        if existing.get("session_id") != session_id:
            blockers.append("idempotency_identity_conflict")
            outcome = "conflict"
        elif existing.get("request_fingerprint") != fingerprint:
            blockers.append("idempotency_fingerprint_conflict")
            outcome = "conflict"
        elif route["goal_action"] == "resume" and (
            (existing.get("authority_pass") or {}).get("cursor")
            != route.get("resume_cursor")
        ):
            blockers.append("idempotency_cursor_conflict")
            outcome = "conflict"
        else:
            session = existing
            outcome = (
                "replayed_completed"
                if existing.get("status") == "complete"
                else "replayed_in_progress"
            )

    goal_action = "create_goal" if route["goal_action"] == "create" else "resume_goal"
    decision = {
        "schema": "goal-entry.decision.v3",
        "request_mode": "execute_goal" if goal_action == "create_goal" else "active_goal_bind",
        "goal_action": goal_action,
        "execution_destination": "goal_lifecycle",
        "request_fingerprint": fingerprint,
        "model_route": route,
        "entry_session": session,
    }
    return decision, blockers, outcome


def resolve_repo_root(raw: str | None, target_paths: list[str]) -> Path | None:
    if raw:
        return Path(raw).expanduser().resolve()
    if target_paths:
        return Path.cwd().resolve()
    return None


def target_exists(repo_root: Path, raw_target: str) -> bool:
    target = Path(raw_target).expanduser()
    if not target.is_absolute():
        target = repo_root / target
    return target.exists()


def load_agents_context(
    args: argparse.Namespace, repo_root: Path, target_paths: list[str]
) -> dict[str, Any]:
    resolver = load_module(GOAL_CONTEXT_RESOLVER, "goal_context_preflight_resolver")
    return resolver.resolve_agents_context(
        SimpleNamespace(
            repo_root=repo_root,
            target_path=target_paths or ["."],
            global_agents=args.global_agents,
            create_missing_global_agents=False,
            create_missing_project_agents=True,
            require_project_agents=True,
            init_doc_workspace=True,
            record_boot=True,
            task_id=args.task_id,
            task_summary=args.task_summary,
            include_content=False,
            include_path_index=True,
            update_project_path_index=True,
            path_index_max_depth=args.path_index_max_depth,
            path_index_max_items=args.path_index_max_items,
        )
    )


def build_preflight(args: argparse.Namespace) -> dict[str, Any]:
    objective_text = read_text_arg(args.objective, args.objective_file)
    route_authority = "model_route"
    idempotency_outcome = "new"
    blockers: list[str] = []
    warnings: list[str] = []

    if args.model_route_json:
        decision, route_blockers, idempotency_outcome = build_model_decision(
            args.model_route_json, args.existing_session_json
        )
        blockers.extend(route_blockers)
        route_objective = (decision.get("model_route") or {}).get("objective") or ""
        if objective_text and route_objective and objective_text != route_objective:
            blockers.append("objective_model_route_mismatch")
        objective_text = route_objective or objective_text
    elif args.legacy_resolver:
        route_authority = "legacy_resolver"
        decision = load_legacy_decision(args, objective_text)
    else:
        decision = {}
        blockers.append("model_route_required")

    entry_session = decision.get("entry_session") or {}
    request_mode = str(decision.get("request_mode"))
    goal_action = str(decision.get("goal_action"))
    readiness_status = str((decision.get("readiness_gate") or {}).get("status"))
    if route_authority == "model_route":
        readiness_status = args.readiness_status
    objective_length = len(objective_text) if objective_text else None
    if objective_length is not None and objective_length > 4000:
        blockers.append("objective_length_over_4000")
    if decision.get("execution_destination") == "goal_lifecycle" and readiness_status != "passed":
        blockers.append(f"readiness_not_passed_for_goal_action:{readiness_status}")

    target_paths = [str(path) for path in args.target_path]
    repo_root = resolve_repo_root(
        str(args.repo_root) if args.repo_root else None, target_paths
    )
    repo_bound = repo_root is not None
    context_required = repo_bound and request_mode in {"execute_goal", "active_goal_bind"}
    agents_context: dict[str, Any] | None = None
    if repo_bound:
        if repo_root is None or not repo_root.exists() or not repo_root.is_dir():
            blockers.append(f"repo_root_missing_or_not_directory:{repo_root}")
        else:
            for target in target_paths or ["."]:
                if not target_exists(repo_root, target):
                    blockers.append(f"target_path_missing:{target}")
            if not blockers:
                agents_context = load_agents_context(args, repo_root, target_paths)
                if agents_context.get("stop_required") is True:
                    blockers.append("goal_context_stop_required")
                warnings.extend(
                    f"goal_context:{warning}"
                    for warning in (agents_context.get("warnings") or [])
                )

    cursor = (entry_session.get("authority_pass") or {}).get("cursor") or {}
    goal_id = cursor.get("goal_id")
    goal_action_allowed = not blockers and decision.get("execution_destination") == "goal_lifecycle"
    return {
        "schema": SCHEMA,
        "ready": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "route_authority": route_authority,
        "request_mode": request_mode,
        "goal_action": goal_action,
        "execution_destination": decision.get("execution_destination"),
        "entry_session_id": entry_session.get("session_id"),
        "request_fingerprint": entry_session.get("request_fingerprint"),
        "lifecycle_state": entry_session.get("lifecycle_state"),
        "goal_id": goal_id,
        "idempotency_outcome": idempotency_outcome,
        "objective_length": objective_length,
        "goal_action_allowed": goal_action_allowed,
        "repo_bound": repo_bound,
        "artifact_run_required": decision.get("execution_destination") == "goal_lifecycle",
        "context_required": context_required,
        "agents_context": agents_context,
        "entry_decision": decision,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run goal execution preflight")
    parser.add_argument("--model-route-json")
    parser.add_argument("--existing-session-json")
    parser.add_argument("--legacy-resolver", action="store_true")
    parser.add_argument("--request")
    parser.add_argument("--request-file")
    parser.add_argument("--objective")
    parser.add_argument("--objective-file")
    parser.add_argument(
        "--conversation-mode", choices=["plan", "default"], default="default"
    )
    parser.add_argument("--active-goal-json")
    parser.add_argument(
        "--readiness-status",
        choices=["auto", "not_required", "pending", "passed", "blocked"],
        default="auto",
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--target-path", action="append", default=[])
    parser.add_argument("--global-agents", type=Path, default=CODEX_HOME / "AGENTS.md")
    parser.add_argument("--task-id", default="goal-preflight")
    parser.add_argument("--task-summary", default="goal preflight context task")
    parser.add_argument("--path-index-max-depth", type=int, default=4)
    parser.add_argument("--path-index-max-items", type=int, default=40)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="output is always JSON")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    payload = build_preflight(args)
    json_text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_text + "\n", encoding="utf-8")
    print(json_text)
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
