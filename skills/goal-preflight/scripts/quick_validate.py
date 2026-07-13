#!/usr/bin/env python3
"""Validate goal-preflight structure and behavior."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_FILES = [
    "SKILL.md",
    "agents/openai.yaml",
    "references/preflight-contract.md",
    "scripts/run_goal_preflight.py",
]
REQUIRED_MARKERS = [
    "$goal-preflight",
    "entry_session_id",
    "request_fingerprint",
    "goal-preflight.preflight.v1",
    "GOAL_ENTRY_RESOLVER",
    "GOAL_CONTEXT_RESOLVER",
    "objective_length_over_4000",
    "ready=false",
]


def read_text(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path}: cannot read: {exc}")
        return ""


def run_json(
    args: list[str], *, expect_returncode: int | None = None
) -> tuple[dict, str, int]:
    proc = subprocess.run(
        [sys.executable, *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if expect_returncode is not None and proc.returncode != expect_returncode:
        raise AssertionError(
            f"expected return code {expect_returncode}, got {proc.returncode}: {proc.stdout}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout is not JSON: {exc}: {proc.stdout}") from exc
    return payload, proc.stdout, proc.returncode


def validate_text(root: Path) -> list[str]:
    errors: list[str] = []
    joined = ""
    for rel in REQUIRED_FILES:
        path = root / rel
        if not path.exists():
            errors.append(f"missing {rel}")
            continue
        joined += "\n" + read_text(path, errors)
    for marker in REQUIRED_MARKERS:
        if marker not in joined:
            errors.append(f"missing marker: {marker}")
    if "$goal-preflight" not in read_text(root / "agents" / "openai.yaml", errors):
        errors.append("agents/openai.yaml default_prompt must mention $goal-preflight")
    return errors


def validate_behavior(root: Path) -> list[str]:
    errors: list[str] = []
    script = root / "scripts" / "run_goal_preflight.py"
    try:
        ready, _, _ = run_json(
            [
                str(script),
                "--request",
                "Please create a long-running Goal to implement this plan",
                "--readiness-status",
                "passed",
                "--objective",
                "Ship the confirmed plan safely.",
            ],
            expect_returncode=0,
        )
        if (
            ready.get("schema") != "goal-preflight.preflight.v1"
            or ready.get("ready") is not True
        ):
            errors.append(f"unexpected ready payload: {ready}")
        if (
            ready.get("goal_action") != "create_goal"
            or ready.get("goal_action_allowed") is not True
        ):
            errors.append(f"unexpected goal action payload: {ready}")

        too_long, _, _ = run_json(
            [
                str(script),
                "--request",
                "Please create a long-running Goal to implement this plan",
                "--readiness-status",
                "passed",
                "--objective",
                "x" * 4001,
            ],
            expect_returncode=1,
        )
        if "objective_length_over_4000" not in too_long.get("blockers", []):
            errors.append(f"overlong objective was not blocked: {too_long}")

        pending, _, _ = run_json(
            [
                str(script),
                "--request",
                "Please create a long-running Goal to implement this plan",
                "--objective",
                "Ship the confirmed plan safely.",
            ],
            expect_returncode=1,
        )
        if pending.get("goal_action_allowed") is not False:
            errors.append(f"pending readiness did not block goal action: {pending}")

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
            context, _, _ = run_json(
                [
                    str(script),
                    "--request",
                    "Please create a long-running Goal to implement this plan",
                    "--readiness-status",
                    "passed",
                    "--objective",
                    "Ship the confirmed plan safely.",
                    "--repo-root",
                    str(repo),
                    "--target-path",
                    "README.md",
                    "--task-id",
                    "preflight-validate",
                ],
                expect_returncode=0,
            )
            if context.get("context_required") is not True or not isinstance(
                context.get("agents_context"), dict
            ):
                errors.append(f"context was not embedded: {context}")
            if (
                context.get("agents_context", {}).get("schema")
                != "goal-context.agents_context.v1"
            ):
                errors.append(f"unexpected agents_context schema: {context}")

            missing, _, _ = run_json(
                [
                    str(script),
                    "--request",
                    "Please create a long-running Goal to implement this plan",
                    "--readiness-status",
                    "passed",
                    "--objective",
                    "Ship the confirmed plan safely.",
                    "--repo-root",
                    str(repo),
                    "--target-path",
                    "missing.py",
                ],
                expect_returncode=1,
            )
            if "target_path_missing:missing.py" not in missing.get("blockers", []):
                errors.append(f"missing target was not blocked: {missing}")
    except Exception as exc:
        errors.append(str(exc))
    return errors


def validate(root: Path) -> list[str]:
    errors = validate_text(root)
    errors.extend(validate_behavior(root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate goal-preflight")
    parser.add_argument(
        "root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        print("FAIL: goal-preflight validation failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: goal-preflight validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
