#!/usr/bin/env python3
"""Validate the compact route selected by the host model.

This module validates an already-made semantic decision.  It deliberately has
no phrase matcher, skill classifier, or fallback route selection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads(
    (ROOT / "references" / "model_route_contract.json").read_text(
        encoding="utf-8"
    )
)


def load_route(value: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raw = str(value)
    if raw.lstrip().startswith("{"):
        loaded = json.loads(raw)
    else:
        loaded = json.loads(Path(raw).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("model route must be a JSON object")
    return loaded


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalized_authorization(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    actions = value.get("external_actions")
    if not isinstance(actions, list) or any(
        not isinstance(action, str) for action in actions
    ):
        return None
    return {
        "scope": str(value.get("scope", "")).strip(),
        "external_actions": sorted(set(actions)),
    }


def validate_model_route(value: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    try:
        route = load_route(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"route_unreadable:{exc}"], "route": {}}

    errors: list[str] = []
    for field in CONTRACT["required_fields"]:
        if field not in route:
            errors.append(f"route_field_missing:{field}")
    if route.get("schema") != CONTRACT["schema"]:
        errors.append("route_schema_invalid")

    level = route.get("execution_level")
    intent = route.get("intent")
    source = route.get("route_source")
    goal_action = route.get("goal_action")
    if level not in CONTRACT["execution_levels"]:
        errors.append("execution_level_invalid")
    if intent not in CONTRACT["intents"]:
        errors.append("intent_invalid")
    if source not in CONTRACT["route_sources"]:
        errors.append("route_source_invalid")
    if goal_action not in CONTRACT["goal_actions"]:
        errors.append("goal_action_invalid")
    if not _nonempty_string(route.get("authoritative_instruction")):
        errors.append("authoritative_instruction_missing")

    if level == "direct" and intent != "read_only":
        errors.append("direct_write_forbidden")
    if intent == "no_execution" and level != "none":
        errors.append("no_execution_conflict")
    if level == "none" and intent != "no_execution":
        errors.append("none_requires_no_execution")
    if level == "goal":
        objective = route.get("objective")
        if not _nonempty_string(objective):
            errors.append("goal_objective_missing")
        elif len(objective) > int(CONTRACT["policies"]["objective_max_characters"]):
            errors.append("goal_objective_over_4000")
        if goal_action not in {"create", "resume"}:
            errors.append("goal_action_required")
        if not _nonempty_string(route.get("idempotency_key")):
            errors.append("goal_idempotency_key_missing")
    elif goal_action is not None:
        errors.append("goal_action_outside_goal_route")

    preferred_skill = route.get("preferred_skill")
    if preferred_skill is not None and not _nonempty_string(preferred_skill):
        errors.append("preferred_skill_invalid")

    authorization = route.get("authorization")
    normalized_authorization = _normalized_authorization(authorization)

    short_reply = route.get("short_reply")
    if not isinstance(short_reply, bool):
        errors.append("short_reply_invalid")
    inherited = route.get("inherited_context")
    if short_reply and source != "inherited_context":
        errors.append("short_reply_requires_inherited_context")
    if source == "inherited_context":
        if not isinstance(inherited, Mapping):
            errors.append("inherited_context_missing")
        else:
            for field in CONTRACT["inherited_task_identity_fields"]:
                if not _nonempty_string(inherited.get(field)):
                    errors.append(f"inherited_{field}_missing")
            for field in CONTRACT["inherited_context_fields"]:
                current = (
                    normalized_authorization
                    if field == "authorization"
                    else route.get(field)
                )
                inherited_value = (
                    _normalized_authorization(inherited.get(field))
                    if field == "authorization"
                    else inherited.get(field)
                )
                if inherited_value != current:
                    errors.append(f"inherited_{field}_mismatch")
            if level == "goal":
                for field in CONTRACT["inherited_goal_context_fields"]:
                    if inherited.get(field) != route.get(field):
                        errors.append(f"inherited_{field}_mismatch")

    if not isinstance(authorization, Mapping):
        errors.append("authorization_missing")
    else:
        if not _nonempty_string(authorization.get("scope")):
            errors.append("authorization_scope_missing")
        actions = authorization.get("external_actions")
        if not isinstance(actions, list) or any(
            action not in CONTRACT["external_actions"] for action in actions
        ):
            errors.append("external_actions_invalid")
        elif len(actions) != len(set(actions)):
            errors.append("external_actions_duplicate")

    if level == "goal" and goal_action == "resume":
        cursor = route.get("resume_cursor")
        if not isinstance(cursor, Mapping):
            errors.append("resume_cursor_missing")
        else:
            if cursor.get("issuer") != "goal-context":
                errors.append("resume_cursor_issuer_invalid")
            if cursor.get("verification_status") != "verified":
                errors.append("resume_cursor_unverified")
            for field in ("goal_id", "revision", "state_source"):
                if cursor.get(field) in {None, ""}:
                    errors.append(f"resume_cursor_{field}_missing")

    normalized = dict(route)
    if normalized_authorization is not None:
        normalized["authorization"] = normalized_authorization
    return {"ok": not errors, "errors": errors, "route": normalized}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a model-owned Goal Entry route")
    parser.add_argument("--route-json", required=True)
    args = parser.parse_args()
    result = validate_model_route(args.route_json)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
