#!/usr/bin/env python3
"""Run the lightweight goal execution preflight gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCHEMA = "goal-preflight.preflight.v1"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
GOAL_ENTRY_RESOLVER = (
    CODEX_HOME / "skills" / "goal-entry" / "scripts" / "resolve_goal_entry.py"
)
GOAL_CONTEXT_RESOLVER = (
    Path(__file__).resolve().parents[2]
    / "goal-context"
    / "scripts"
    / "ensure_agents_context.py"
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


def load_goal_entry_decision(
    args: argparse.Namespace, objective_text: str
) -> dict[str, Any]:
    resolver = load_module(GOAL_ENTRY_RESOLVER, "goal_entry_preflight_resolver")
    return resolver.resolve(
        SimpleNamespace(
            request=args.request,
            request_file=args.request_file,
            objective=objective_text,
            objective_file=None,
            conversation_mode=args.conversation_mode,
            active_goal_json=args.active_goal_json,
            readiness_status=args.readiness_status,
        )
    )


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
    objective_length = len(objective_text) if objective_text else None
    decision = load_goal_entry_decision(args, objective_text)
    entry_session = decision.get("entry_session") or {}
    request_mode = str(decision.get("request_mode"))
    goal_action = str(decision.get("goal_action"))
    readiness_status = str((decision.get("readiness_gate") or {}).get("status"))
    target_paths = [str(path) for path in args.target_path]
    repo_root = resolve_repo_root(
        str(args.repo_root) if args.repo_root else None, target_paths
    )
    repo_bound = repo_root is not None
    context_required = repo_bound and request_mode in {
        "execute_goal",
        "active_goal_bind",
    }
    blockers: list[str] = []
    warnings: list[str] = []
    agents_context: dict[str, Any] | None = None

    if objective_length is not None and objective_length > 4000:
        blockers.append("objective_length_over_4000")

    if goal_action == "fallback_handoff" and request_mode in {
        "execute_goal",
        "active_goal_bind",
    }:
        if readiness_status != "passed":
            blockers.append(f"readiness_not_passed_for_goal_action:{readiness_status}")

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
                for warning in agents_context.get("warnings") or []:
                    warnings.append(f"goal_context:{warning}")
    elif request_mode in {"execute_goal", "active_goal_bind"} and decision.get(
        "run_dir_required"
    ):
        warnings.append("repo_root_not_provided_for_artifact_capable_execution")

    goal_action_allowed = not any(
        blocker.startswith("objective_length_over_4000")
        or blocker.startswith("readiness_not_passed_for_goal_action")
        for blocker in blockers
    )

    return {
        "schema": SCHEMA,
        "ready": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "request_mode": request_mode,
        "goal_action": goal_action,
        "execution_destination": decision.get("execution_destination"),
        "entry_session_id": entry_session.get("session_id"),
        "request_fingerprint": entry_session.get("request_fingerprint"),
        "objective_length": objective_length,
        "goal_action_allowed": goal_action_allowed,
        "repo_bound": repo_bound,
        "artifact_run_required": bool(decision.get("run_dir_required")),
        "context_required": context_required,
        "agents_context": agents_context,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run goal execution preflight")
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
    parser.add_argument(
        "--global-agents", type=Path, default=CODEX_HOME / "AGENTS.md"
    )
    parser.add_argument("--task-id", default="goal-preflight")
    parser.add_argument("--task-summary", default="goal preflight context task")
    parser.add_argument("--path-index-max-depth", type=int, default=4)
    parser.add_argument("--path-index-max-items", type=int, default=40)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="accepted for compatibility; output is always JSON",
    )
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
