from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_EXPERTS = {
    "implementation",
    "debugging",
    "test_and_verification",
    "architecture_and_code_review",
    "research_and_experiment",
    "documentation_and_communication",
    "release_and_reliability",
    "security_and_risk",
    "frontend_and_ui_engineering",
}
EXPECTED_DOMAINS = {
    "implementation",
    "debugging",
    "verification",
    "architecture",
    "research",
    "documentation",
    "release",
    "security",
    "frontend",
}
GOVERNED_CLAIMS = {"code", "experiment", "release", "security"}


def validate_registries(expert_path: Path, family_path: Path) -> dict:
    experts = json.loads(expert_path.read_text(encoding="utf-8"))
    families = json.loads(family_path.read_text(encoding="utf-8"))
    errors = []
    records = experts.get("experts") or []
    ids = [item.get("id") for item in records]
    if set(ids) != EXPECTED_EXPERTS or len(ids) != len(EXPECTED_EXPERTS):
        errors.append(
            "expert catalog must contain the nine stable classes exactly once"
        )
    domains = [domain for item in records for domain in item.get("primary_domains", [])]
    if set(domains) != EXPECTED_DOMAINS or len(domains) != len(EXPECTED_DOMAINS):
        errors.append("expert catalog must map the nine primary domains exactly once")
    accepted_claims = {
        claim for item in records for claim in item.get("accepts_claims", [])
    }
    if accepted_claims != GOVERNED_CLAIMS:
        errors.append("expert catalog must cover every governed claim type")
    known_families = set((families.get("families") or {}).keys())
    for item in records:
        unknown = set(item.get("families", [])) - known_families
        if unknown:
            errors.append(f"{item.get('id')}: unknown families {sorted(unknown)}")
    deny = families.get("global_deny") or {}
    denied = set(deny.get("skills", [])) | set(deny.get("goal_tools", []))
    prefixes = tuple(deny.get("prefixes", []))
    for family_id, family in (families.get("families") or {}).items():
        for skill in family.get("skills", []):
            if skill in denied or skill.startswith(prefixes):
                errors.append(f"{family_id}: globally denied skill {skill}")
    return {"ok": not errors, "errors": errors, "expert_count": len(records)}


def main() -> int:
    backend_refs = Path(__file__).resolve().parents[2] / "goal-backend" / "references"
    parser = argparse.ArgumentParser(
        description="Validate reviewed expert and skill-family registries."
    )
    parser.add_argument(
        "--expert-registry", type=Path, default=backend_refs / "expert-registry.json"
    )
    parser.add_argument(
        "--family-registry",
        type=Path,
        default=backend_refs / "skill-family-registry.json",
    )
    args = parser.parse_args()
    result = validate_registries(args.expert_registry, args.family_registry)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
