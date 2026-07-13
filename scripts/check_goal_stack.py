from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


MANIFEST_NAME = "goal-stack-manifest.json"
SKILL_NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
FORBIDDEN_REQUIRED_REFERENCES = (
    "harness_mode",
    "superpowers_subagents",
    "Superpowers-first",
)


def load_manifest(source: Path) -> Dict[str, Any]:
    value = json.loads((source / MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "goal-stack-package/v1":
        raise ValueError("invalid goal stack manifest schema")
    skills = value.get("skills")
    if not isinstance(skills, list) or not skills:
        raise ValueError("manifest skills must be a non-empty list")
    if len(skills) != len(set(skills)):
        raise ValueError("manifest skills contain duplicates")
    public_entry = value.get("public_entry", "goal-entry")
    if public_entry != "goal-entry":
        raise ValueError("manifest public_entry must be goal-entry")
    for name in skills:
        if not isinstance(name, str) or not SKILL_NAME_RE.fullmatch(name):
            raise ValueError(f"invalid manifest skill name: {name!r}")
        if name in {"goal-entry", "harness-agent"}:
            raise ValueError(f"manifest must not own public/removed skill: {name}")
    return value


def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and not path.name.endswith(".pyc")
        ):
            yield path


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in iter_files(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _has_symlink_component(path: Path) -> bool:
    absolute = Path(os.path.abspath(str(path.expanduser())))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _skill_name(skill_file: Path) -> str | None:
    text = skill_file.read_text(encoding="utf-8")
    match = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", text)
    return match.group(1) if match else None


def check_source(source: Path) -> Dict[str, Any]:
    source = source.resolve()
    errors: List[str] = []
    try:
        manifest = load_manifest(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"manifest:{exc}"]}
    public_skill = source / "SKILL.md"
    if not public_skill.is_file():
        errors.append("public goal-entry SKILL.md is missing")
    elif _skill_name(public_skill) != "goal-entry":
        errors.append("public SKILL.md frontmatter name must be goal-entry")
    public_agent = source / "agents" / "openai.yaml"
    if not public_agent.is_file():
        errors.append("public goal-entry agents/openai.yaml is missing")
    elif "$goal-entry" not in public_agent.read_text(encoding="utf-8"):
        errors.append("public goal-entry default_prompt must mention $goal-entry")
    for name in manifest["skills"]:
        skill_root = source / "skills" / name
        skill_file = skill_root / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{name}: SKILL.md missing")
            continue
        if _skill_name(skill_file) != name:
            errors.append(f"{name}: frontmatter name mismatch")
        agent_file = skill_root / "agents" / "openai.yaml"
        if not agent_file.is_file():
            errors.append(f"{name}: agents/openai.yaml missing")
        else:
            agent_text = agent_file.read_text(encoding="utf-8")
            if f"${name}" not in agent_text:
                errors.append(f"{name}: default_prompt must mention ${name}")
            if "allow_implicit_invocation: false" not in agent_text:
                errors.append(
                    f"{name}: internal skill must disable implicit invocation"
                )
        for path in iter_files(skill_root):
            if path.suffix.lower() not in {".md", ".py", ".json", ".yaml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_REQUIRED_REFERENCES:
                if forbidden in text:
                    errors.append(
                        f"{path.relative_to(source)}: forbidden required reference {forbidden!r}"
                    )
            if path.suffix == ".json":
                try:
                    json.loads(text)
                except json.JSONDecodeError as exc:
                    errors.append(
                        f"{path.relative_to(source)}: invalid JSON: {exc.msg}"
                    )
    try:
        experts = json.loads(
            (
                source
                / "skills"
                / "goal-backend"
                / "references"
                / "expert-registry.json"
            ).read_text()
        )
        families = json.loads(
            (
                source
                / "skills"
                / "goal-backend"
                / "references"
                / "skill-family-registry.json"
            ).read_text()
        )
        if len(experts.get("experts", [])) != 9:
            errors.append("expert registry must contain exactly nine experts")
        deny = families.get("global_deny") or {}
        denied = set(deny.get("skills", [])) | set(deny.get("goal_tools", []))
        prefixes = tuple(deny.get("prefixes", []))
        for family_id, family in (families.get("families") or {}).items():
            for skill in family.get("skills", []):
                if skill in denied or skill.startswith(prefixes):
                    errors.append(
                        f"family {family_id} contains globally denied skill {skill}"
                    )
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"registry:{exc}")
    return {
        "ok": not errors,
        "errors": errors,
        "skills": manifest["skills"],
        "source_digest": tree_digest(source / "skills"),
    }


def check_installed(source: Path, destination: Path) -> Dict[str, Any]:
    source = source.resolve()
    source_result = check_source(source)
    errors = list(source_result.get("errors", []))
    if _has_symlink_component(destination):
        errors.append("destination root is symlinked")
        return {"ok": False, "errors": errors}
    destination = destination.resolve()
    if (destination / "harness-agent").exists() or (
        destination / "harness-agent"
    ).is_symlink():
        errors.append("installed harness-agent must be absent")
    if not destination.is_dir():
        errors.append("destination root missing")
        return {"ok": False, "errors": errors}
    try:
        manifest = load_manifest(source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": errors + [f"manifest:{exc}"]}
    for name in manifest["skills"]:
        expected = source / "skills" / name
        actual = destination / name
        if not actual.is_dir() or actual.is_symlink():
            errors.append(f"installed skill missing or symlinked: {name}")
            continue
        if tree_digest(expected) != tree_digest(actual):
            errors.append(f"installed skill drift: {name}")
    return {"ok": not errors, "errors": errors, "skills": manifest["skills"]}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the Goal stack package or installation."
    )
    parser.add_argument("source", nargs="?", default=".", type=Path)
    parser.add_argument("--installed-root", type=Path)
    args = parser.parse_args()
    result = (
        check_installed(args.source, args.installed_root)
        if args.installed_root
        else check_source(args.source)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
