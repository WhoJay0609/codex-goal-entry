from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
BACKEND_SCRIPTS = ROOT / "skills" / "goal-backend" / "scripts"
METADATA_SCRIPTS = ROOT / "skills" / "goal-metadata" / "scripts"


def load_script(name: str) -> ModuleType:
    path = BACKEND_SCRIPTS / name
    if str(BACKEND_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(BACKEND_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_top_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / name
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_metadata_script(name: str) -> ModuleType:
    path = METADATA_SCRIPTS / name
    if str(METADATA_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(METADATA_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def authorization(
    owner: str = "goal-dispatch",
    capability: str = "run.initialize",
    *,
    actor: str = "main_orchestrator",
    ready: bool = True,
    execution_allowed: bool = True,
) -> dict:
    fingerprint = "a" * 64
    return {
        "actor": actor,
        "owner_skill": owner,
        "capability": capability,
        "goal_id": "goal-123",
        "entry_decision": {
            "execution_destination": "goal_lifecycle",
            "request_fingerprint": fingerprint,
            "entry_session": {
                "version": 2,
                "session_id": "entry-0123456789abcdef0123",
                "status": "in_progress",
                "request_fingerprint": fingerprint,
                "semantic_pass": {"status": "resolved"},
                "authority_pass": {
                    "status": "ready" if execution_allowed else "planning_only",
                    "goal_mutation_allowed": True,
                    "phase_execution_allowed": execution_allowed,
                    "cursor": {"goal_id": "goal-123"},
                },
            },
        },
        "goal_preflight": {
            "ready": ready,
            "entry_session_id": "entry-0123456789abcdef0123",
            "request_fingerprint": fingerprint,
            "goal_id": "goal-123",
        },
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
