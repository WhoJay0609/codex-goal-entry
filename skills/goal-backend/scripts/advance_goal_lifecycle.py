from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from goal_backend_common import (
    append_goal_event,
    authorize,
    ensure_goal_event,
    load_json_value,
    load_manifest,
    read_jsonl,
    validate_run_binding,
    write_json_atomic,
)


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references" / "lifecycle-contract.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
WORK_STATUSES = {"planned", "active", "accepted", "failed", "blocked"}
WORK_RISKS = {"low", "medium", "high"}
GOVERNED_CLAIMS = {"code", "experiment", "release", "security"}


def _dependency_cycle(work_units: list[Mapping[str, Any]]) -> bool:
    dependencies = {
        str(unit.get("id")): list(unit.get("dependencies") or [])
        for unit in work_units
        if isinstance(unit, Mapping) and unit.get("id")
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(unit_id: str) -> bool:
        if unit_id in visiting:
            return True
        if unit_id in visited:
            return False
        visiting.add(unit_id)
        if any(visit(str(dependency)) for dependency in dependencies.get(unit_id, [])):
            return True
        visiting.remove(unit_id)
        visited.add(unit_id)
        return False

    return any(visit(unit_id) for unit_id in dependencies)


def _projection_errors(manifest: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    graph = manifest.get("task_graph") or {}
    projections = manifest.get("issue_projections") or {}
    if not isinstance(graph, Mapping):
        return ["task_graph_invalid"]
    if not isinstance(projections, Mapping):
        return ["issue_projections_invalid"]
    for milestone in graph.get("milestones", []):
        if not isinstance(milestone, Mapping):
            continue
        projection = projections.get(f"milestone:{milestone.get('id')}")
        if not isinstance(projection, Mapping) or projection.get("status") not in {
            "applied",
            "draft",
        }:
            errors.append(f"milestone_issue_projection_missing:{milestone.get('id')}")
    for mapping_key, projection in projections.items():
        if not isinstance(projection, Mapping) or projection.get("status") not in {
            "applied",
            "draft",
        }:
            errors.append(f"issue_projection_not_ready:{mapping_key}")
    return errors


def _verification_evidence_errors(
    graph: Mapping[str, Any], run_dir: Path
) -> list[str]:
    from check_independent_acceptance import check_acceptance

    errors: list[str] = []
    rows, row_errors = read_jsonl(run_dir / "events.jsonl")
    errors.extend(row_errors)
    for milestone in graph.get("milestones", []):
        milestone_id = milestone.get("id")
        candidates = [
            row
            for row in rows
            if row.get("kind") == "milestone_acceptance"
            and (row.get("data") or {}).get("milestone_id") == milestone_id
        ]
        if not candidates:
            errors.append(f"milestone_mechanical_evidence_missing:{milestone_id}")
            continue
        evidence = candidates[-1]
        data = evidence.get("data") or {}
        references = data.get("evidence_refs")
        if (
            evidence.get("status") != "completed"
            or data.get("mechanical_passed") is not True
            or not isinstance(references, list)
            or not references
            or any(not isinstance(item, str) or not item.strip() for item in references)
        ):
            errors.append(f"milestone_mechanical_evidence_invalid:{milestone_id}")

    acceptance_rows = [
        row
        for row in rows
        if row.get("kind") == "independent_acceptance"
        and row.get("status") == "completed"
    ]
    for unit in graph.get("work_units", []):
        if unit.get("risk") != "high":
            continue
        unit_id = unit.get("id")
        claims = [
            row
            for row in rows
            if row.get("kind") == "claim"
            and (row.get("data") or {}).get("work_unit_id") == unit_id
        ]
        if not claims or claims[-1].get("status") != "completed":
            errors.append(f"high_risk_claim_missing:{unit_id}")
            continue
        claim = claims[-1].get("data") or {}
        claim_id = claim.get("claim_id")
        claim_type = claim.get("claim_type")
        if (
            not isinstance(claim_id, str)
            or not claim_id.strip()
            or claim_type not in GOVERNED_CLAIMS
        ):
            errors.append(f"high_risk_claim_invalid:{unit_id}")
            continue
        candidates = [
            row
            for row in acceptance_rows
            if (row.get("data") or {}).get("claim_id") == claim_id
        ]
        accepted = False
        invalid_reasons: set[str] = set()
        for candidate in candidates:
            acceptance = candidate.get("data") or {}
            verdict = check_acceptance(
                claim_type=str(claim_type),
                executor_id=str(claim.get("executor_id", "")),
                verifier_id=str(acceptance.get("verifier_id", "")),
                verifier_expert=str(acceptance.get("verifier_expert", "")),
                accepted=acceptance.get("accepted") is True,
            )
            if verdict["accepted"]:
                accepted = True
                break
            invalid_reasons.update(verdict["reasons"])
        if not accepted:
            errors.append(f"high_risk_independent_acceptance_missing:{unit_id}")
            errors.extend(
                f"high_risk_independent_acceptance_invalid:{unit_id}:{reason}"
                for reason in sorted(invalid_reasons)
            )

    handles, handle_errors = read_jsonl(run_dir / "runtime_handles.jsonl")
    errors.extend(handle_errors)
    if any(handle.get("status") in {None, "active", "running"} for handle in handles):
        cleanup_rows, cleanup_errors = read_jsonl(run_dir / "cleanup.jsonl")
        errors.extend(cleanup_errors)
        if not cleanup_rows or cleanup_rows[-1].get("status") != "completed":
            errors.append("runtime_cleanup_incomplete_before_verifying")
    return errors


def _graph_errors(graph: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if graph.get("version") != 1:
        errors.append("task_graph_version_invalid")
    milestones = graph.get("milestones")
    work_units = graph.get("work_units")
    if not isinstance(milestones, list) or not milestones:
        errors.append("task_graph_milestones_missing")
        milestones = []
    if not isinstance(work_units, list) or not work_units:
        errors.append("task_graph_work_units_missing")
        work_units = []
    milestone_ids = [item.get("id") for item in milestones if isinstance(item, Mapping)]
    unit_ids = [item.get("id") for item in work_units if isinstance(item, Mapping)]
    if len(milestone_ids) != len(set(milestone_ids)) or any(not item for item in milestone_ids):
        errors.append("task_graph_milestone_ids_invalid")
    if len(unit_ids) != len(set(unit_ids)) or any(not item for item in unit_ids):
        errors.append("task_graph_unit_ids_invalid")
    for milestone in milestones:
        if not isinstance(milestone, Mapping):
            errors.append("task_graph_milestone_invalid")
            continue
        criteria = milestone.get("acceptance_criteria")
        if not isinstance(criteria, list) or not criteria or any(
            not isinstance(item, str) or not item.strip() for item in criteria
        ):
            errors.append(f"milestone_acceptance_missing:{milestone.get('id')}")
        if milestone.get("status", "planned") not in WORK_STATUSES:
            errors.append(f"milestone_status_invalid:{milestone.get('id')}")
    for unit in work_units:
        if not isinstance(unit, Mapping):
            errors.append("task_graph_work_unit_invalid")
            continue
        if unit.get("milestone_id") not in milestone_ids:
            errors.append(f"work_unit_milestone_missing:{unit.get('id')}")
        dependencies = unit.get("dependencies")
        if (
            not isinstance(dependencies, list)
            or any(not isinstance(dependency, str) for dependency in dependencies)
            or len(dependencies) != len(set(dependencies))
            or unit.get("id") in dependencies
            or any(dep not in unit_ids for dep in dependencies)
        ):
            errors.append(f"work_unit_dependencies_invalid:{unit.get('id')}")
        if unit.get("status", "planned") not in WORK_STATUSES:
            errors.append(f"work_unit_status_invalid:{unit.get('id')}")
        if unit.get("risk") not in WORK_RISKS:
            errors.append(f"work_unit_risk_invalid:{unit.get('id')}")
    valid_units = [unit for unit in work_units if isinstance(unit, Mapping)]
    if not any(error.startswith("work_unit_dependencies_invalid:") for error in errors):
        if _dependency_cycle(valid_units):
            errors.append("task_graph_dependency_cycle")
    return errors


def store_task_graph(
    request: Mapping[str, Any], run_dir: Path, graph: Mapping[str, Any]
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "authorization": decision, "errors": decision["reasons"]}
    errors = validate_run_binding(run_dir, decision)
    if request.get("capability") != "evidence.record":
        errors.append("wrong_capability")
    errors.extend(_graph_errors(graph))
    try:
        manifest = load_manifest(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"manifest_invalid:{exc}"]}
    if manifest.get("lifecycle_state") not in {"planning", "active"}:
        errors.append("task_graph_state_invalid")
    existing_units = {
        item.get("id"): item
        for item in (manifest.get("task_graph") or {}).get("work_units", [])
        if isinstance(item, Mapping)
    }
    candidate_units = {
        item.get("id"): item
        for item in graph.get("work_units", [])
        if isinstance(item, Mapping)
    }
    for unit_id, existing in existing_units.items():
        if existing.get("status") == "accepted" and candidate_units.get(unit_id) != existing:
            errors.append(f"accepted_work_unit_immutable:{unit_id}")
    existing_milestones = {
        item.get("id"): item
        for item in (manifest.get("task_graph") or {}).get("milestones", [])
        if isinstance(item, Mapping)
    }
    candidate_milestones = {
        item.get("id"): item
        for item in graph.get("milestones", [])
        if isinstance(item, Mapping)
    }
    for milestone_id, existing in existing_milestones.items():
        if (
            existing.get("status") == "accepted"
            and candidate_milestones.get(milestone_id) != existing
        ):
            errors.append(f"accepted_milestone_immutable:{milestone_id}")
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}
    manifest["task_graph"] = json.loads(json.dumps(graph))
    write_json_atomic(run_dir / "manifest.json", manifest)
    event = append_goal_event(
        run_dir,
        decision,
        kind="task_graph_recorded",
        status="completed",
        data={
            "milestone_ids": [item["id"] for item in graph["milestones"]],
            "work_unit_ids": [item["id"] for item in graph["work_units"]],
        },
    )
    return {"ok": True, "manifest": manifest, "event": event}


def update_work_status(
    request: Mapping[str, Any],
    run_dir: Path,
    *,
    work_units: Mapping[str, str],
    milestones: Mapping[str, str],
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "errors": decision["reasons"], "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    if request.get("capability") != "evidence.record":
        errors.append("wrong_capability")
    manifest = load_manifest(run_dir)
    graph = manifest.get("task_graph") or {}
    unit_rows = {item.get("id"): item for item in graph.get("work_units", [])}
    milestone_rows = {item.get("id"): item for item in graph.get("milestones", [])}
    for item_id, status in work_units.items():
        if item_id not in unit_rows:
            errors.append(f"work_unit_unknown:{item_id}")
        elif status not in WORK_STATUSES:
            errors.append(f"work_unit_status_invalid:{item_id}")
        elif unit_rows[item_id].get("status") == "accepted" and status != "accepted":
            errors.append(f"accepted_work_unit_immutable:{item_id}")
    for item_id, status in milestones.items():
        if item_id not in milestone_rows:
            errors.append(f"milestone_unknown:{item_id}")
        elif status not in WORK_STATUSES:
            errors.append(f"milestone_status_invalid:{item_id}")
        elif milestone_rows[item_id].get("status") == "accepted" and status != "accepted":
            errors.append(f"accepted_milestone_immutable:{item_id}")
    prospective_units = {
        item_id: work_units.get(item_id, row.get("status", "planned"))
        for item_id, row in unit_rows.items()
    }
    for item_id, status in work_units.items():
        if item_id not in unit_rows or status not in {"active", "accepted"}:
            continue
        for dependency in unit_rows[item_id].get("dependencies", []):
            if prospective_units.get(dependency) != "accepted":
                errors.append(
                    f"work_unit_dependency_not_accepted:{item_id}:{dependency}"
                )
    for milestone_id, status in milestones.items():
        if milestone_id not in milestone_rows or status != "accepted":
            continue
        milestone_units = [
            item_id
            for item_id, row in unit_rows.items()
            if row.get("milestone_id") == milestone_id
        ]
        if not milestone_units or any(
            prospective_units.get(item_id) != "accepted"
            for item_id in milestone_units
        ):
            errors.append(f"milestone_work_units_not_accepted:{milestone_id}")
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}
    for item_id, status in work_units.items():
        unit_rows[item_id]["status"] = status
    for item_id, status in milestones.items():
        milestone_rows[item_id]["status"] = status
    write_json_atomic(run_dir / "manifest.json", manifest)
    event = append_goal_event(
        run_dir,
        decision,
        kind="work_status_updated",
        status="completed",
        data={"work_units": dict(work_units), "milestones": dict(milestones)},
    )
    return {"ok": True, "manifest": manifest, "event": event}


def _transition_errors(manifest: Mapping[str, Any], run_dir: Path, target: str) -> list[str]:
    current = manifest.get("lifecycle_state")
    errors: list[str] = []
    graph = manifest.get("task_graph") or {}
    if target == "blocked":
        sync_rows, sync_errors = read_jsonl(run_dir / "goal_sync.jsonl")
        errors.extend(sync_errors)
        if not any(
            row.get("phase") == "pre_update"
            and row.get("goal_status") == "blocked"
            for row in sync_rows
        ) or not any(
            row.get("phase") == "post_update"
            and row.get("goal_status") == "blocked"
            and row.get("update_called") is True
            for row in sync_rows
        ):
            errors.append("goal_sync_blocked_evidence_missing")
    elif current == "planning" and target == "active":
        if not isinstance(graph, Mapping):
            errors.append("task_graph_invalid")
        else:
            graph_errors = _graph_errors(graph)
            errors.extend(graph_errors)
            if not graph_errors:
                errors.extend(_projection_errors(manifest))
    elif current == "active" and target == "verifying":
        if not isinstance(graph, Mapping):
            errors.append("task_graph_invalid")
        else:
            graph_errors = _graph_errors(graph)
            errors.extend(graph_errors)
            if not graph_errors:
                for unit in graph["work_units"]:
                    if unit.get("status") != "accepted":
                        errors.append(f"work_unit_not_accepted:{unit.get('id')}")
                for milestone in graph["milestones"]:
                    if milestone.get("status") != "accepted":
                        errors.append(
                            f"milestone_not_accepted:{milestone.get('id')}"
                        )
                errors.extend(_projection_errors(manifest))
                errors.extend(_verification_evidence_errors(graph, run_dir))
    elif current == "verifying" and target == "completed":
        from check_independent_acceptance import check_acceptance

        cleanup_rows, cleanup_errors = read_jsonl(run_dir / "cleanup.jsonl")
        errors.extend(cleanup_errors)
        if not cleanup_rows or cleanup_rows[-1].get("status") != "completed":
            errors.append("runtime_cleanup_incomplete")
        pr = manifest.get("pr_projection")
        if "pr.create" not in set(manifest.get("external_actions") or []):
            errors.append("pr_create_not_authorized")
        if not isinstance(pr, Mapping) or pr.get("status") != "applied":
            errors.append("authorized_pr_evidence_missing")
        elif pr.get("provider_state") != "open":
            errors.append("authorized_pr_not_open")
        rows, row_errors = read_jsonl(run_dir / "events.jsonl")
        errors.extend(row_errors)
        claims = [
            row for row in rows
            if row.get("kind") == "claim"
            and (row.get("data") or {}).get("claim_id") == "final-pr"
            and row.get("status") == "completed"
        ]
        acceptances = [
            row for row in rows
            if row.get("kind") == "independent_acceptance"
            and (row.get("data") or {}).get("claim_id") == "final-pr"
            and row.get("status") == "completed"
            and (row.get("data") or {}).get("accepted") is True
        ]
        if not claims or not acceptances:
            errors.append("final_independent_acceptance_missing")
        else:
            claim = claims[-1].get("data") or {}
            acceptance = acceptances[-1].get("data") or {}
            if claim.get("claim_type") != "release":
                errors.append("final_pr_claim_type_invalid")
            if isinstance(pr, Mapping) and (
                claim.get("provider_id") != pr.get("provider_id")
                or claim.get("desired_state_digest")
                != pr.get("desired_state_digest")
            ):
                errors.append("final_pr_claim_projection_mismatch")
            verdict = check_acceptance(
                claim_type=str(claim.get("claim_type", "")),
                executor_id=str(claim.get("executor_id", "")),
                verifier_id=str(acceptance.get("verifier_id", "")),
                verifier_expert=str(acceptance.get("verifier_expert", "")),
                accepted=acceptance.get("accepted") is True,
            )
            errors.extend(
                f"final_independent_acceptance_invalid:{reason}"
                for reason in verdict["reasons"]
            )
        sync_rows, sync_errors = read_jsonl(run_dir / "goal_sync.jsonl")
        errors.extend(sync_errors)
        if not any(
            row.get("phase") == "pre_update" and row.get("goal_status") == "complete"
            for row in sync_rows
        ) or not any(
            row.get("phase") == "post_update"
            and row.get("goal_status") == "complete"
            and row.get("update_called") is True
            for row in sync_rows
        ):
            errors.append("goal_sync_complete_evidence_missing")
    return errors


def _replay_transition(
    manifest: Mapping[str, Any],
    run_dir: Path,
    decision: Mapping[str, Any],
    *,
    target_state: str,
    expected_revision: int,
) -> dict | None:
    last_transition = manifest.get("last_transition")
    if not isinstance(last_transition, Mapping):
        return None
    if not (
        manifest.get("lifecycle_state") == target_state
        and manifest.get("lifecycle_revision") == expected_revision + 1
        and last_transition.get("to") == target_state
        and last_transition.get("revision") == expected_revision + 1
    ):
        return None
    ensured = ensure_goal_event(
        run_dir,
        decision,
        kind="lifecycle_transition",
        status="blocked" if target_state == "blocked" else "completed",
        data=dict(last_transition),
        identity_fields=("revision", "to"),
    )
    if not ensured["ok"]:
        return {
            "ok": False,
            "errors": ensured["errors"],
            "authorization": decision,
        }
    return {
        "ok": True,
        "manifest": dict(manifest),
        "event": ensured["event"],
        "replayed": True,
    }


def advance_lifecycle(
    request: Mapping[str, Any],
    run_dir: Path,
    *,
    target_state: str,
    expected_revision: int,
) -> dict:
    decision = authorize(request)
    if not decision["allowed"]:
        return {"ok": False, "errors": decision["reasons"], "authorization": decision}
    errors = validate_run_binding(run_dir, decision)
    manifest = load_manifest(run_dir)
    current = manifest.get("lifecycle_state")
    if not errors:
        replay = _replay_transition(
            manifest,
            run_dir,
            decision,
            target_state=target_state,
            expected_revision=expected_revision,
        )
        if replay is not None:
            return replay
    if manifest.get("lifecycle_revision") != expected_revision:
        errors.append("lifecycle_revision_conflict")
    if target_state not in (CONTRACT["transitions"].get(current) or []):
        errors.append("lifecycle_transition_invalid")
    required_capability = CONTRACT["transition_capabilities"].get(
        f"{current}->{target_state}"
    )
    if required_capability and request.get("capability") != required_capability:
        errors.append("lifecycle_transition_capability_mismatch")
    if not errors:
        errors.extend(_transition_errors(manifest, run_dir, target_state))
    if errors:
        return {"ok": False, "errors": errors, "authorization": decision}
    manifest["lifecycle_state"] = target_state
    manifest["lifecycle_revision"] = expected_revision + 1
    manifest["last_transition"] = {
        "from": current,
        "to": target_state,
        "revision": manifest["lifecycle_revision"],
    }
    write_json_atomic(run_dir / "manifest.json", manifest)
    event = append_goal_event(
        run_dir,
        decision,
        kind="lifecycle_transition",
        status="completed" if target_state != "blocked" else "blocked",
        data=manifest["last_transition"],
    )
    return {"ok": True, "manifest": manifest, "event": event}


def main() -> int:
    parser = argparse.ArgumentParser(description="Advance a Goal lifecycle state")
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--target-state", required=True, choices=CONTRACT["states"])
    parser.add_argument("--expected-revision", required=True, type=int)
    args = parser.parse_args()
    result = advance_lifecycle(
        load_json_value(args.authorization_json),
        args.run_dir,
        target_state=args.target_state,
        expected_revision=args.expected_revision,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
