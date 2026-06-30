#!/usr/bin/env python3
"""Validate the standalone goal-entry package."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "scripts/resolve_goal_entry.py",
    "references/architecture.md",
    "agents/openai.yaml",
]
ENTRY_MARKERS = [
    "$goal-entry",
    "resolve_goal_entry.py",
    "only source of truth",
    "4,000 characters",
    "goal-preflight",
    "goal-objective",
    "goal-context",
    "goal-dispatch",
    "goal-close",
]


def read_text(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path}: cannot read: {exc}")
        return ""


def load_router(path: Path):
    spec = importlib.util.spec_from_file_location("goal_entry_resolver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["goal_entry_resolver"] = module
    spec.loader.exec_module(module)
    return module


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for rel_path in REQUIRED_FILES:
        if not (root / rel_path).exists():
            errors.append(f"missing required file: {rel_path}")

    entry_text = read_text(root / "SKILL.md", errors)
    for marker in ENTRY_MARKERS:
        if marker not in entry_text:
            errors.append(f"SKILL.md missing marker: {marker}")

    openai_text = read_text(root / "agents" / "openai.yaml", errors)
    if "$goal-entry" not in openai_text:
        errors.append("agents/openai.yaml default_prompt must mention $goal-entry")

    router_path = root / "scripts" / "resolve_goal_entry.py"
    try:
        router = load_router(router_path)
        decision = router.resolve(
            SimpleNamespace(
                request="PLEASE IMPLEMENT THIS PLAN with tests",
                request_file=None,
                active_goal_json=None,
                readiness_status="passed",
                superpowers_available="true",
                direct_runtime_requested=False,
                objective=None,
                objective_file=None,
                conversation_mode="default",
            )
        )
        if decision["request_mode"] != "execute_goal":
            errors.append(f"unexpected request_mode: {decision['request_mode']}")
        if decision["goal_action"] != "create_goal":
            errors.append(f"unexpected goal_action: {decision['goal_action']}")
    except Exception as exc:
        errors.append(f"resolver import/use failed: {exc}")

    proc = subprocess.run(
        [
            sys.executable,
            str(router_path),
            "--request",
            "PLEASE IMPLEMENT THIS PLAN",
            "--readiness-status",
            "passed",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        errors.append(f"resolver CLI failed: {proc.stdout.strip()}")
    else:
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            errors.append(f"resolver CLI did not emit JSON: {exc}")
        else:
            if payload.get("request_mode") != "execute_goal":
                errors.append(f"resolver CLI unexpected request_mode: {payload.get('request_mode')}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate standalone goal-entry")
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        print("FAIL: standalone goal-entry validation failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: standalone goal-entry validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
