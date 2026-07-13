#!/usr/bin/env python3
"""Validate the model-native goal-entry package and legacy read surfaces."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


sys.dont_write_bytecode = True

REQUIRED_FILES = [
    "VERSION",
    "CHANGELOG.md",
    "SKILL.md",
    "README.md",
    "goal-stack-manifest.json",
    "scripts/validate_model_route.py",
    "scripts/resolve_goal_entry.py",
    "scripts/validate_goal_runtime.py",
    "references/model_route_contract.json",
    "references/entry_session_contract.json",
    "references/runtime_profiles.json",
    "skills/goal-preflight/scripts/run_goal_preflight.py",
    "skills/goal-backend/references/lifecycle-contract.json",
    "skills/goal-backend/scripts/advance_goal_lifecycle.py",
    "skills/goal-backend/scripts/sync_issue_projection.py",
    "skills/goal-backend/scripts/record_recovery_action.py",
    "tests/fixtures/model_route_cases.json",
    "tests/fixtures/engineering_runtime_trace.json",
    "tests/fixtures/autoresearch_runtime_trace.json",
]
ENTRY_MARKERS = [
    "$goal-entry",
    "goal-entry.model-route.v1",
    "direct",
    "compound",
    "goal",
    "none",
    "Compound Engineering",
    "goal-preflight",
    "planning -> active -> verifying -> completed",
    "preferred_skill",
]


def read_text(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path}: cannot read: {exc}")
        return ""


def load_module(path: Path, name: str):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_json(command: list[str], *, cwd: Path) -> tuple[int, dict, str]:
    proc = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    return proc.returncode, payload, proc.stdout.strip()


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for rel_path in REQUIRED_FILES:
        if not (root / rel_path).exists():
            errors.append(f"missing required file: {rel_path}")

    version = read_text(root / "VERSION", errors).strip()
    if len(version.split(".")) != 3 or not all(
        part.isdigit() for part in version.split(".")
    ):
        errors.append(f"VERSION must use MAJOR.MINOR.PATCH: {version!r}")
    changelog = read_text(root / "CHANGELOG.md", errors)
    if version and f"## [{version}]" not in changelog:
        errors.append(f"CHANGELOG.md missing current VERSION entry: {version}")
    try:
        package_manifest = json.loads(
            read_text(root / "goal-stack-manifest.json", errors)
        )
        if package_manifest.get("version") != version:
            errors.append("goal-stack-manifest version does not match VERSION")
    except json.JSONDecodeError as exc:
        errors.append(f"goal-stack-manifest is invalid JSON: {exc}")

    entry_text = read_text(root / "SKILL.md", errors)
    for marker in ENTRY_MARKERS:
        if marker not in entry_text:
            errors.append(f"SKILL.md missing marker: {marker}")
    if "scripts/resolve_goal_entry.py" in entry_text:
        errors.append("SKILL.md must not instruct normal runtime to call the legacy resolver")
    if len(entry_text.splitlines()) > 100:
        errors.append("SKILL.md exceeded the 100-line thin-router budget")

    try:
        contract = json.loads(
            read_text(root / "references" / "model_route_contract.json", errors)
        )
        if contract.get("execution_levels") != ["direct", "compound", "goal", "none"]:
            errors.append("model-route execution levels changed unexpectedly")
        serialized = json.dumps(contract, ensure_ascii=False).lower()
        if "marker_groups" in serialized or "regex" in serialized:
            errors.append("model-route contract contains semantic classification rules")
        validator = load_module(
            root / "scripts" / "validate_model_route.py", "quick_model_route_validator"
        )
        cases = json.loads(
            read_text(root / "tests" / "fixtures" / "model_route_cases.json", errors)
        )
        for case in cases:
            result = validator.validate_model_route(case["route"])
            if result["ok"] is not case["valid"]:
                errors.append(f"model-route fixture mismatch: {case['name']}")
            if case.get("error") and case["error"] not in result["errors"]:
                errors.append(f"model-route fixture missed error: {case['name']}")
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        errors.append(f"model-route validation failed: {exc}")

    legacy_code, legacy, legacy_output = run_json(
        [
            sys.executable,
            str(root / "scripts" / "resolve_goal_entry.py"),
            "--request",
            "PLEASE IMPLEMENT THIS PLAN with tests",
            "--readiness-status",
            "passed",
        ],
        cwd=root,
    )
    if legacy_code != 0 or not legacy:
        errors.append(f"legacy resolver diagnostics failed: {legacy_output}")
    elif legacy.get("execution_destination") != "compound_engineering":
        errors.append("legacy resolver compatibility projection changed")

    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    test_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(root / "tests"),
            "-p",
            "test_*.py",
        ],
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

    stack_code, stack, stack_output = run_json(
        [sys.executable, str(root / "scripts" / "check_goal_stack.py"), str(root)],
        cwd=root,
    )
    if stack_code != 0 or not stack.get("ok"):
        errors.append(f"goal stack validation failed: {stack_output}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate standalone goal-entry")
    parser.add_argument(
        "root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1]
    )
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
