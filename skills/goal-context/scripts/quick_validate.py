#!/usr/bin/env python3
"""Validate goal-context structure and resolver behavior."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


REQUIRED_FILES = [
    "SKILL.md",
    "agents/openai.yaml",
    "references/agents-md-hierarchy.md",
    "scripts/ensure_agents_context.py",
]
REQUIRED_MARKERS = [
    "goal-context",
    "AGENTS.md",
    "Path Index",
    "agents_context.json",
    "doc/",
    "stop_required=true",
    "goal-context:path-index",
    "harness-agents-md-context:path-index",
    "harness-agent-for-goal:path-index",
    "orchestrator-only",
]


def read_text(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path}: cannot read: {exc}")
        return ""


def load_resolver(root: Path) -> Any:
    script_path = root / "scripts" / "ensure_agents_context.py"
    spec = importlib.util.spec_from_file_location("goal_context", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["goal_context"] = module
    spec.loader.exec_module(module)
    return module


def validate_text(root: Path) -> list[str]:
    errors: list[str] = []
    texts: list[str] = []
    for rel in REQUIRED_FILES:
        path = root / rel
        if not path.exists():
            errors.append(f"missing {rel}")
            continue
        texts.append(read_text(path, errors))
    joined = "\n".join(texts)
    for marker in REQUIRED_MARKERS:
        if marker not in joined:
            errors.append(f"missing marker: {marker}")
    if "$goal-context" not in read_text(root / "agents" / "openai.yaml", errors):
        errors.append("agents/openai.yaml default_prompt must mention $goal-context")
    return errors


def validate_resolver(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        resolver = load_resolver(root)
    except Exception as exc:
        return [f"ensure_agents_context.py: cannot load resolver: {exc}"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = tmp_path / "repo"
        target_dir = repo / "src" / "pkg"
        target_dir.mkdir(parents=True)
        (repo / "README.md").write_text("# Example Repo\n", encoding="utf-8")
        (repo / "pyproject.toml").write_text(
            '[project]\nname = "example"\n', encoding="utf-8"
        )
        (repo / "tests").mkdir()
        (repo / "tests" / "test_example.py").write_text(
            "def test_example():\n    assert True\n", encoding="utf-8"
        )
        (target_dir / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        global_agents = tmp_path / "global" / "AGENTS.md"
        payload = resolver.resolve_agents_context(
            SimpleNamespace(
                repo_root=repo,
                target_path=["src/pkg/module.py"],
                global_agents=global_agents,
                create_missing_global_agents=True,
                create_missing_project_agents=True,
                require_project_agents=True,
                init_doc_workspace=True,
                record_boot=True,
                task_id="eval-agents-context",
                task_summary="validate agents context",
                include_content=False,
                include_path_index=True,
                update_project_path_index=True,
                path_index_max_depth=4,
                path_index_max_items=20,
            )
        )
        if payload.get("schema") != "goal-context.agents_context.v1":
            errors.append(f"unexpected schema: {payload.get('schema')}")
        if payload.get("stop_required") is not False:
            errors.append(
                f"expected clean generated context, got {json.dumps(payload, ensure_ascii=False)}"
            )
        chain = payload.get("targets", [{}])[0].get("agents_chain", [])
        scopes = [row.get("scope") for row in chain]
        if scopes != ["global", "project"]:
            errors.append(f"wrong generated chain scopes {scopes}")
        for path in [
            repo / "AGENTS.md",
            repo / "doc" / "task_plan.md",
            repo / "doc" / "lessons.md",
        ]:
            if not path.exists():
                errors.append(f"missing generated path {path}")
        project_text = (repo / "AGENTS.md").read_text(encoding="utf-8")
        for marker in [
            resolver.PATH_INDEX_BEGIN,
            "## Path Index",
            "`src/pkg/module.py`",
            "`pyproject.toml`",
            resolver.PATH_INDEX_END,
        ]:
            if marker not in project_text:
                errors.append(f"project AGENTS.md missing marker {marker}")

        legacy_text = (
            "# Existing AGENTS.md\n\n"
            f"{resolver.LEGACY_PATH_INDEX_MARKERS[0][0]}\nold\n{resolver.LEGACY_PATH_INDEX_MARKERS[0][1]}\n"
        )
        (repo / "AGENTS.md").write_text(legacy_text, encoding="utf-8")
        migrated = resolver.resolve_agents_context(
            SimpleNamespace(
                repo_root=repo,
                target_path=["src/pkg/module.py"],
                global_agents=global_agents,
                create_missing_global_agents=False,
                create_missing_project_agents=False,
                require_project_agents=True,
                init_doc_workspace=False,
                record_boot=False,
                task_id="eval-agents-context",
                task_summary="validate agents context",
                include_content=False,
                include_path_index=True,
                update_project_path_index=True,
                path_index_max_depth=4,
                path_index_max_items=20,
            )
        )
        if (
            migrated.get("project_agents", {}).get("path_index_action")
            != "migrated_legacy"
        ):
            errors.append("legacy Path Index block was not migrated")
        migrated_text = (repo / "AGENTS.md").read_text(encoding="utf-8")
        if (
            resolver.LEGACY_PATH_INDEX_MARKERS[0][0] in migrated_text
            or resolver.PATH_INDEX_BEGIN not in migrated_text
        ):
            errors.append("legacy Path Index markers remain after migration")

        (repo / "progress.md").write_text(
            "# Wrong root process doc\n", encoding="utf-8"
        )
        blocked = resolver.resolve_agents_context(
            SimpleNamespace(
                repo_root=repo,
                target_path=["src/pkg/module.py"],
                global_agents=global_agents,
                create_missing_global_agents=False,
                create_missing_project_agents=False,
                require_project_agents=True,
                init_doc_workspace=False,
                record_boot=False,
                task_id="eval-agents-context",
                task_summary="validate agents context",
                include_content=False,
                include_path_index=False,
                update_project_path_index=False,
                path_index_max_depth=4,
                path_index_max_items=20,
            )
        )
        if blocked.get("stop_required") is not True:
            errors.append("root process doc violation did not stop execution")
    return errors


def validate(root: Path) -> list[str]:
    errors = validate_text(root)
    errors.extend(validate_resolver(root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate goal-context")
    parser.add_argument(
        "path", nargs="?", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()

    root = args.path.resolve()
    errors = validate(root)
    if errors:
        print("FAIL: goal-context validation failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: goal-context validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
