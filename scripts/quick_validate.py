#!/usr/bin/env python3
"""Validate the standalone goal-entry package."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


sys.dont_write_bytecode = True


REQUIRED_FILES = [
    "VERSION",
    "CHANGELOG.md",
    "SKILL.md",
    "README.md",
    "scripts/resolve_goal_entry.py",
    "scripts/validate_goal_runtime.py",
    "references/architecture.md",
    "references/runtime_profiles.json",
    "agents/openai.yaml",
    "tests/fixtures/engineering_runtime_trace.json",
    "tests/fixtures/autoresearch_runtime_trace.json",
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
    "decision_contract",
    "Runtime Profile",
    "Claim Firewall",
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

    version = read_text(root / "VERSION", errors).strip()
    if not version or not all(part.isdigit() for part in version.split(".")) or len(version.split(".")) != 3:
        errors.append(f"VERSION must use MAJOR.MINOR.PATCH: {version!r}")
    changelog_text = read_text(root / "CHANGELOG.md", errors)
    if version and f"## [{version}]" not in changelog_text:
        errors.append(f"CHANGELOG.md missing current VERSION entry: {version}")

    entry_text = read_text(root / "SKILL.md", errors)
    for marker in ENTRY_MARKERS:
        if marker not in entry_text:
            errors.append(f"SKILL.md missing marker: {marker}")

    openai_text = read_text(root / "agents" / "openai.yaml", errors)
    if "$goal-entry" not in openai_text:
        errors.append("agents/openai.yaml default_prompt must mention $goal-entry")

    contract_text = read_text(root / "references" / "runtime_profiles.json", errors)
    try:
        runtime_contract = json.loads(contract_text)
    except json.JSONDecodeError as exc:
        errors.append(f"runtime profile contract is invalid JSON: {exc}")
    else:
        profiles = runtime_contract.get("profiles", {})
        if set(profiles) != {"complex_engineering", "scientific_autoresearch"}:
            errors.append(f"unexpected runtime profiles: {sorted(profiles)}")
        capabilities = runtime_contract.get("capabilities", {})
        if any(owner in {"subagent", "runtime_subagent"} for owner in capabilities.values()):
            errors.append("runtime capability grants Goal authority to a subagent")

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
        contract = decision.get("decision_contract", {})
        if contract.get("task_profile") != "complex_engineering":
            errors.append(f"unexpected task_profile: {contract.get('task_profile')}")
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

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    test_proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests")],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if test_proc.returncode != 0:
        errors.append(f"unit tests failed: {test_proc.stdout.strip()}")

    runtime_proc = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "validate_goal_runtime.py"),
            str(root / "tests" / "fixtures" / "engineering_runtime_trace.json"),
            str(root / "tests" / "fixtures" / "autoresearch_runtime_trace.json"),
        ],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if runtime_proc.returncode != 0:
        errors.append(f"runtime trace validation failed: {runtime_proc.stdout.strip()}")
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
