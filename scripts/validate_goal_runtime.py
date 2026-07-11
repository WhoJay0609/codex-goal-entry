#!/usr/bin/env python3
"""Replay Goal runtime traces against the portable conformance contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime_profiles.json"
RUNTIME_CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
SHARED_KERNEL = RUNTIME_CONTRACT["shared_kernel"]


def violation(result: dict[str, Any], index: int, message: str) -> None:
    result["violations"].append(f"event {index}: {message}")


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def validate_trace(trace: dict[str, Any]) -> dict[str, Any]:
    trace = require_mapping(trace, "trace")
    profile = trace.get("profile")
    profiles = RUNTIME_CONTRACT["profiles"]
    if profile not in profiles:
        raise ValueError(f"unknown runtime profile: {profile}")
    events = trace.get("events")
    if not isinstance(events, list):
        raise ValueError("trace events must be a JSON array")

    result: dict[str, Any] = {
        "profile": profile,
        "violations": [],
        "terminal_state": "open",
        "accepted_milestones": [],
        "unresolved_subagents": [],
        "experiment_count": 0,
        "claims": {},
    }
    roadmap_approved = False
    goal_created = False
    milestones: dict[str, dict[str, Any]] = {}
    agents: dict[str, dict[str, Any]] = {}
    drifted_branches: set[str] = set()
    invalidated_providers: set[str] = set()
    checkpointed_providers: set[str] = set()
    experiments: dict[str, dict[str, Any]] = {}
    retry_limit = profiles[profile]["max_corrective_retries"]

    for index, raw_event in enumerate(events, start=1):
        if not isinstance(raw_event, dict):
            violation(result, index, "event must be an object")
            continue
        event_type = raw_event.get("type")

        if event_type == "goal_created":
            goal_created = True
            continue

        if event_type == "roadmap_approved":
            if not goal_created:
                violation(result, index, "roadmap approval requires a created Goal")
            roadmap_approved = True
            continue

        if event_type == "milestone_started":
            milestone_id = str(raw_event.get("milestone_id", ""))
            if not milestone_id:
                violation(result, index, "milestone start requires milestone_id")
                continue
            if milestone_id in milestones:
                violation(result, index, f"milestone cannot be restarted or overwrite accepted evidence: {milestone_id}")
                continue
            if not roadmap_approved:
                violation(result, index, "milestone cannot start before roadmap approval")
            dependencies = raw_event.get("dependencies", [])
            if not isinstance(dependencies, list):
                violation(result, index, "milestone dependencies must be an array")
                dependencies = []
            unaccepted = [item for item in dependencies if milestones.get(str(item), {}).get("status") != "accepted"]
            if unaccepted:
                violation(result, index, f"milestone dependencies are not accepted: {unaccepted}")
            milestones[milestone_id] = {
                "status": "active",
                "implementer": None,
                "evidence": False,
                "retries": 0,
            }
            continue

        if event_type == "subagent_started":
            agent_id = str(raw_event.get("agent_id", ""))
            milestone_id = str(raw_event.get("milestone_id", ""))
            if milestone_id not in milestones:
                violation(result, index, "subagent requires an active milestone")
            if agent_id in agents and not agents[agent_id].get("cleaned"):
                violation(result, index, "duplicate subagent ownership requires reclamation")
            agents[agent_id] = {"milestone_id": milestone_id, "terminal": False, "cleaned": False}
            continue

        if event_type == "subagent_terminal":
            agent_id = str(raw_event.get("agent_id", ""))
            if agent_id not in agents:
                violation(result, index, "terminal event references unknown subagent")
            else:
                agents[agent_id]["terminal"] = True
                agents[agent_id]["outcome"] = raw_event.get("outcome")
            continue

        if event_type == "subagent_cleanup":
            agent_id = str(raw_event.get("agent_id", ""))
            if agent_id not in agents:
                violation(result, index, "cleanup references unknown subagent")
            elif not agents[agent_id]["terminal"]:
                violation(result, index, "cleanup requires a terminal subagent record")
            else:
                agents[agent_id]["cleaned"] = True
                agents[agent_id]["disposition"] = raw_event.get("disposition")
            continue

        if event_type == "milestone_evidence":
            milestone_id = str(raw_event.get("milestone_id", ""))
            milestone = milestones.get(milestone_id)
            if not milestone:
                violation(result, index, "evidence references unknown milestone")
            else:
                milestone["implementer"] = raw_event.get("implementer")
                milestone["evidence"] = bool(raw_event.get("artifacts"))
                if not milestone["evidence"]:
                    violation(result, index, "milestone evidence requires at least one artifact")
            continue

        if event_type == "milestone_verdict":
            milestone_id = str(raw_event.get("milestone_id", ""))
            milestone = milestones.get(milestone_id)
            if not milestone:
                violation(result, index, "verdict references unknown milestone")
                continue
            verdict = raw_event.get("verdict")
            if verdict not in SHARED_KERNEL["verdicts"]:
                violation(result, index, f"unknown milestone verdict: {verdict}")
                continue
            verifier = raw_event.get("verifier")
            independent = verifier and verifier != milestone.get("implementer")
            if not independent:
                violation(result, index, "milestone acceptance requires an independent verifier")
            pending_cleanup = [
                agent_id
                for agent_id, state in agents.items()
                if state.get("milestone_id") == milestone_id and not state.get("cleaned")
            ]
            if verdict == "passed" and pending_cleanup:
                violation(result, index, f"milestone acceptance requires cleanup evidence for {pending_cleanup}")
            if verdict == "passed" and not milestone.get("evidence"):
                violation(result, index, "milestone acceptance requires submitted evidence")
            if verdict == "passed" and independent and milestone.get("evidence") and not pending_cleanup:
                milestone["status"] = "accepted"
            else:
                milestone["status"] = "blocked"
            milestone["verdict"] = verdict
            continue

        if event_type == "corrective_retry":
            milestone_id = str(raw_event.get("milestone_id", ""))
            milestone = milestones.get(milestone_id)
            if not milestone:
                violation(result, index, "retry references unknown milestone")
            else:
                if milestone.get("verdict") not in {"failed", "evidence_insufficient"}:
                    violation(result, index, "corrective retry requires a failed verdict")
                milestone["retries"] += 1
                if milestone["retries"] > retry_limit:
                    violation(result, index, f"profile retry limit exceeded for {milestone_id}")
            continue

        if event_type == "replan_unfinished":
            milestone_id = raw_event.get("milestone_id")
            candidates = [milestones.get(str(milestone_id))] if milestone_id else list(milestones.values())
            retry_exhausted = any(
                milestone
                and milestone.get("verdict") in {"failed", "evidence_insufficient"}
                and milestone.get("retries", 0) >= retry_limit
                for milestone in candidates
            )
            if not retry_exhausted:
                violation(result, index, "replan requires an exhausted retry budget")
            if raw_event.get("boundary_changed"):
                violation(result, index, "replan cannot change a locked boundary without owner approval")
            if not raw_event.get("preserves_accepted"):
                violation(result, index, "replan must preserve accepted milestone evidence")
            continue

        if event_type == "drift_detected":
            drifted_branches.add(str(raw_event.get("branch", "")))
            continue

        if event_type == "provider_attestation_invalidated":
            provider_id = str(raw_event.get("provider_id", ""))
            if not provider_id or not raw_event.get("reason"):
                violation(result, index, "provider invalidation requires provider_id and reason")
            else:
                invalidated_providers.add(provider_id)
                checkpointed_providers.discard(provider_id)
            continue

        if event_type == "provider_safe_checkpoint":
            provider_id = str(raw_event.get("provider_id", ""))
            if provider_id not in invalidated_providers:
                violation(result, index, "safe checkpoint requires an invalidated provider")
            elif not raw_event.get("checkpoint_ref"):
                violation(result, index, "safe checkpoint requires checkpoint_ref")
            else:
                checkpointed_providers.add(provider_id)
            continue

        if event_type == "provider_attestation_renegotiated":
            provider_id = str(raw_event.get("provider_id", ""))
            if provider_id not in invalidated_providers:
                violation(result, index, "provider renegotiation requires an invalidated provider")
            elif provider_id not in checkpointed_providers:
                violation(result, index, "provider renegotiation requires a safe checkpoint")
            elif raw_event.get("compatible") is True:
                invalidated_providers.remove(provider_id)
                checkpointed_providers.discard(provider_id)
            continue

        if event_type == "provider_phase_resumed":
            provider_id = str(raw_event.get("provider_id", ""))
            if provider_id in invalidated_providers:
                violation(result, index, "provider phase cannot resume while attestation is invalidated")
            continue

        if event_type == "provider_phase_paused":
            provider_id = str(raw_event.get("provider_id", ""))
            if provider_id and provider_id not in invalidated_providers:
                violation(result, index, "provider pause requires an invalidated provider")
            continue

        if event_type == "branch_mutation":
            branch = str(raw_event.get("branch", ""))
            if branch in drifted_branches:
                violation(result, index, f"mutation attempted on paused drifted branch {branch}")
            if invalidated_providers:
                violation(result, index, f"mutation attempted with invalidated provider {sorted(invalidated_providers)}")
            continue

        if event_type == "drift_corrected":
            branch = str(raw_event.get("branch", ""))
            if branch not in drifted_branches:
                violation(result, index, f"drift correction references unpaused branch {branch}")
            elif not raw_event.get("basis"):
                violation(result, index, "drift correction requires an accepted reconciliation basis")
            else:
                drifted_branches.remove(branch)
            continue

        if event_type == "experiment_result":
            experiment_id = str(raw_event.get("experiment_id", ""))
            experiments[experiment_id] = dict(raw_event)
            continue

        if event_type == "claim_proposed":
            claim_id = str(raw_event.get("claim_id", ""))
            experiment = experiments.get(str(raw_event.get("experiment_id", "")))
            if not experiment:
                violation(result, index, "claim requires traceable experiment evidence")
                continue
            integrity = experiment.get("integrity_status")
            verdict = experiment.get("evidence_verdict")
            if integrity != "passed" or verdict == "evidence_insufficient":
                violation(result, index, "claim firewall blocks integrity failure or insufficient evidence")
            elif verdict in {"warning", "partial_support"}:
                if raw_event.get("qualified") is not True:
                    violation(result, index, "claim firewall requires qualified narrowing for warning or partial support")
                else:
                    result["claims"][claim_id] = "qualified"
            elif verdict == "supported":
                result["claims"][claim_id] = "allowed"
            else:
                violation(result, index, f"claim firewall received unknown evidence verdict: {verdict}")
            continue

        if event_type == "goal_closed":
            unaccepted = [key for key, value in milestones.items() if value.get("status") != "accepted"]
            unresolved = [key for key, value in agents.items() if not value.get("cleaned")]
            if not roadmap_approved:
                violation(result, index, "goal close requires roadmap approval")
            if not milestones or not any(value.get("status") == "accepted" for value in milestones.values()):
                violation(result, index, "goal close requires at least one accepted milestone")
            if unaccepted:
                violation(result, index, f"goal close requires accepted milestones: {unaccepted}")
            if unresolved:
                violation(result, index, f"goal close requires zero unresolved subagents: {unresolved}")
            if drifted_branches:
                violation(result, index, f"goal close requires corrected drift: {sorted(drifted_branches)}")
            if invalidated_providers:
                violation(result, index, f"goal close requires compatible provider recovery: {sorted(invalidated_providers)}")
            if profile == "scientific_autoresearch" and (not experiments or not result["claims"]):
                violation(result, index, "scientific closeout requires a traceable claim disposition")
            if (
                roadmap_approved
                and milestones
                and any(value.get("status") == "accepted" for value in milestones.values())
                and not unaccepted
                and not unresolved
                and not drifted_branches
                and not invalidated_providers
                and (profile != "scientific_autoresearch" or (experiments and result["claims"]))
            ):
                result["terminal_state"] = "closed"
            continue

        violation(result, index, f"unknown event type: {event_type}")

    result["accepted_milestones"] = sorted(
        milestone_id for milestone_id, state in milestones.items() if state.get("status") == "accepted"
    )
    result["unresolved_subagents"] = sorted(
        agent_id for agent_id, state in agents.items() if not state.get("cleaned")
    )
    result["experiment_count"] = len(experiments)
    if result["terminal_state"] == "open":
        result["violations"].append("trace did not reach clean closeout")
    if result["violations"]:
        result["terminal_state"] = "invalid"
    return result


def validate_trace_file(path: Path) -> dict[str, Any]:
    return validate_trace(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Goal runtime conformance traces")
    parser.add_argument("traces", nargs="+", type=Path)
    args = parser.parse_args(argv)
    results = []
    failed = False
    for path in args.traces:
        result = validate_trace_file(path)
        results.append({"path": str(path), **result})
        failed = failed or bool(result["violations"])
    json.dump(results, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
