from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import load_json_value, utc_now
from record_goal_evidence import record_evidence


REFERENCE_ROOT = Path(__file__).resolve().parents[1] / "references"


def _expert(experts: Mapping[str, Any], expert_id: str) -> Mapping[str, Any] | None:
    for item in experts.get("experts", []):
        if isinstance(item, Mapping) and item.get("id") == expert_id:
            return item
    return None


def _globally_denied(skill: str, families: Mapping[str, Any]) -> bool:
    deny = families.get("global_deny") or {}
    return (
        skill in deny.get("skills", [])
        or skill in deny.get("goal_tools", [])
        or any(skill.startswith(prefix) for prefix in deny.get("prefixes", []))
    )


def authorize_expert_skill(
    expert_id: str,
    skill: str,
    experts: Mapping[str, Any],
    families: Mapping[str, Any],
) -> dict:
    result = {
        "allowed": False,
        "expert_id": expert_id,
        "skill": skill,
        "checked_at": utc_now(),
        "registry_version": experts.get("version"),
        "family_registry_version": families.get("version"),
    }
    if _globally_denied(skill, families):
        result["reason"] = "global_deny"
        return result
    expert = _expert(experts, expert_id)
    if expert is None:
        result["reason"] = "unknown_expert"
        return result
    for family_id in expert.get("families", []):
        family = (families.get("families") or {}).get(family_id) or {}
        if skill in family.get("skills", []):
            result.update(
                {
                    "allowed": True,
                    "reason": "registered_family_member",
                    "family": family_id,
                }
            )
            return result
    result["reason"] = "skill_not_in_expert_families"
    return result


def authorize_and_record_expert_skill(
    request: Mapping[str, Any],
    run_dir: Path,
    expert_id: str,
    skill: str,
    experts: Mapping[str, Any],
    families: Mapping[str, Any],
) -> dict:
    decision = authorize_expert_skill(expert_id, skill, experts, families)
    evidence = record_evidence(
        request,
        run_dir,
        kind="expert_skill_authorization",
        status="completed" if decision["allowed"] else "blocked",
        data=decision,
    )
    result = dict(decision)
    result["evidence_recorded"] = evidence.get("ok") is True
    result["evidence"] = evidence
    if not result["evidence_recorded"]:
        result["allowed"] = False
        result["reason"] = "permission_evidence_not_recorded"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize an expert's use of one registered skill."
    )
    parser.add_argument("--expert", required=True)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--expert-registry", type=Path, default=REFERENCE_ROOT / "expert-registry.json"
    )
    parser.add_argument(
        "--family-registry",
        type=Path,
        default=REFERENCE_ROOT / "skill-family-registry.json",
    )
    args = parser.parse_args()
    experts = json.loads(args.expert_registry.read_text(encoding="utf-8"))
    families = json.loads(args.family_registry.read_text(encoding="utf-8"))
    result = authorize_and_record_expert_skill(
        load_json_value(args.authorization_json),
        args.run_dir,
        args.expert,
        args.skill,
        experts,
        families,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
