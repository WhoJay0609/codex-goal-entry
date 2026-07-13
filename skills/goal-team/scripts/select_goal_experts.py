from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List


EXPERT_REGISTRY = (
    Path(__file__).resolve().parents[2]
    / "goal-backend"
    / "references"
    / "expert-registry.json"
)
EXPERTS = json.loads(EXPERT_REGISTRY.read_text(encoding="utf-8"))["experts"]
DOMAIN_EXPERTS = {
    domain: expert["id"]
    for expert in EXPERTS
    for domain in expert.get("primary_domains", [])
}
CLAIM_VERIFIERS = {
    claim: [
        expert["id"] for expert in EXPERTS if claim in expert.get("accepts_claims", [])
    ]
    for claim in ("code", "experiment", "release", "security")
}


def select_experts(
    primary_domain: str, cross_domains: Iterable[str], claim_type: str
) -> Dict:
    if primary_domain not in DOMAIN_EXPERTS:
        raise ValueError(f"unknown primary domain: {primary_domain}")
    primary = DOMAIN_EXPERTS[primary_domain]
    cross_domains = tuple(cross_domains)
    team: List[Dict[str, str]] = [
        {"role": "primary", "expert": primary, "instance_id": f"primary-{primary}"}
    ]
    selected = {primary}
    for domain in cross_domains:
        if domain not in DOMAIN_EXPERTS:
            raise ValueError(f"unknown cross domain: {domain}")
        expert = DOMAIN_EXPERTS[domain]
        if expert in selected:
            continue
        team.append(
            {
                "role": "cross_domain_specialist",
                "expert": expert,
                "instance_id": f"specialist-{expert}",
            }
        )
        selected.add(expert)
    if claim_type in CLAIM_VERIFIERS:
        candidates = CLAIM_VERIFIERS[claim_type]
        if not candidates:
            raise ValueError(f"no verifier registered for claim type: {claim_type}")
        verifier = next((item for item in candidates if item != primary), candidates[0])
        team.append(
            {
                "role": "independent_verifier",
                "expert": verifier,
                "instance_id": f"verifier-{verifier}",
                "claim_type": claim_type,
            }
        )
    elif claim_type != "read_only":
        raise ValueError(f"unknown claim type: {claim_type}")
    return {
        "primary_domain": primary_domain,
        "cross_domains": list(cross_domains),
        "claim_type": claim_type,
        "team": team,
        "selection_rule": "one_primary_plus_required_specialists_and_independent_verifier",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select the minimum expert set for one Goal unit."
    )
    parser.add_argument(
        "--primary-domain", required=True, choices=sorted(DOMAIN_EXPERTS)
    )
    parser.add_argument("--cross-domain", action="append", default=[])
    parser.add_argument(
        "--claim-type", default="read_only", choices=["read_only", *CLAIM_VERIFIERS]
    )
    args = parser.parse_args()
    print(
        json.dumps(
            select_experts(args.primary_domain, args.cross_domain, args.claim_type),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
