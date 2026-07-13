from __future__ import annotations

import argparse
import json
from pathlib import Path

from goal_backend_common import utc_now


EXPERT_REGISTRY = (
    Path(__file__).resolve().parents[1] / "references" / "expert-registry.json"
)
EXPERTS = json.loads(EXPERT_REGISTRY.read_text(encoding="utf-8"))["experts"]
ELIGIBLE = {
    claim: {
        expert["id"] for expert in EXPERTS if claim in expert.get("accepts_claims", [])
    }
    for claim in ("code", "experiment", "release", "security")
}


def check_acceptance(
    *,
    claim_type: str,
    executor_id: str,
    verifier_id: str,
    verifier_expert: str,
    accepted: bool,
) -> dict:
    reasons = []
    governed = claim_type in ELIGIBLE
    if not accepted:
        reasons.append("verifier_did_not_accept")
    if governed and not executor_id.strip():
        reasons.append("executor_id_missing")
    if governed and not verifier_id.strip():
        reasons.append("verifier_id_missing")
    if governed and executor_id == verifier_id:
        reasons.append("verifier_not_independent")
    if governed and verifier_expert not in ELIGIBLE[claim_type]:
        reasons.append("verifier_expert_not_eligible")
    if not governed and claim_type != "read_only":
        reasons.append("claim_type_unknown")
    return {
        "accepted": not reasons,
        "claim_type": claim_type,
        "executor_id": executor_id,
        "verifier_id": verifier_id,
        "verifier_expert": verifier_expert,
        "independent_required": governed,
        "reasons": reasons,
        "checked_at": utc_now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check risk-based independent acceptance."
    )
    parser.add_argument("--claim-type", required=True)
    parser.add_argument("--executor-id", required=True)
    parser.add_argument("--verifier-id", required=True)
    parser.add_argument("--verifier-expert", required=True)
    parser.add_argument("--accepted", action="store_true")
    args = parser.parse_args()
    result = check_acceptance(
        claim_type=args.claim_type,
        executor_id=args.executor_id,
        verifier_id=args.verifier_id,
        verifier_expert=args.verifier_expert,
        accepted=args.accepted,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
