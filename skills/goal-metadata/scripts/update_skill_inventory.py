from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _frontmatter_name(text: str, fallback: str) -> str:
    match = re.search(r"(?m)^name:\s*([^\s]+)\s*$", text)
    if not match:
        return fallback
    value = match.group(1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value or fallback


def build_inventory(skills_root: Path, family_registry: Path) -> dict:
    registry = json.loads(family_registry.read_text(encoding="utf-8"))
    families = registry.get("families") or {}
    registered = {
        skill: family_id
        for family_id, family in families.items()
        for skill in family.get("skills", [])
    }
    deny = registry.get("global_deny") or {}
    denied = set(deny.get("skills", [])) | set(deny.get("goal_tools", []))
    prefixes = tuple(deny.get("prefixes", []))
    installed = []
    if skills_root.is_dir():
        for directory in sorted(
            path for path in skills_root.iterdir() if path.is_dir()
        ):
            skill_file = directory / "SKILL.md"
            if not skill_file.is_file():
                continue
            installed.append(
                _frontmatter_name(
                    skill_file.read_text(encoding="utf-8"), directory.name
                )
            )
    return {
        "schema": "goal-skill-inventory/v1",
        "installed": installed,
        "registered": sorted(skill for skill in installed if skill in registered),
        "unregistered": sorted(
            skill
            for skill in installed
            if skill not in registered
            and skill not in denied
            and not skill.startswith(prefixes)
        ),
        "globally_denied": sorted(
            skill
            for skill in installed
            if skill in denied or skill.startswith(prefixes)
        ),
        "auto_grants": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report installed, registered, and unregistered skills."
    )
    parser.add_argument("--skills-root", required=True, type=Path)
    parser.add_argument(
        "--family-registry",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "goal-backend"
        / "references"
        / "skill-family-registry.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_inventory(args.skills_root, args.family_registry)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
