from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a non-mutating Goal stack health report."
    )
    parser.add_argument("--skills-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    inventory_module = _load("goal_inventory", here / "update_skill_inventory.py")
    registry_module = _load("goal_registries", here / "update_expert_registry.py")
    refs = Path(__file__).resolve().parents[2] / "goal-backend" / "references"
    inventory = inventory_module.build_inventory(
        args.skills_root, refs / "skill-family-registry.json"
    )
    registries = registry_module.validate_registries(
        refs / "expert-registry.json", refs / "skill-family-registry.json"
    )
    result = {
        "schema": "goal-stack-health/v1",
        "ok": registries["ok"],
        "registries": registries,
        "inventory": inventory,
        "permission_drift": inventory["unregistered"],
        "automatic_permissions_added": [],
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
