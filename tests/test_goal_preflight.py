from __future__ import annotations

import importlib.util
import json
import sys
import unittest

from support import ROOT


def load_preflight():
    path = ROOT / "skills" / "goal-preflight" / "scripts" / "run_goal_preflight.py"
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("goal_preflight_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREFLIGHT = load_preflight()
CASES = json.loads(
    (ROOT / "tests" / "fixtures" / "model_route_cases.json").read_text(
        encoding="utf-8"
    )
)


def route(name: str) -> dict:
    return dict(next(item["route"] for item in CASES if item["name"] == name))


def run_route(value: dict, *extra: str) -> dict:
    args = PREFLIGHT.parse_args(
        ["--model-route-json", json.dumps(value), "--readiness-status", "passed", *extra]
    )
    return PREFLIGHT.build_preflight(args)


class GoalPreflightTests(unittest.TestCase):
    def test_goal_route_creates_stable_planning_session(self) -> None:
        first = run_route(route("model_upgrades_project_to_goal"))
        second = run_route(route("model_upgrades_project_to_goal"))
        self.assertTrue(first["ready"])
        self.assertEqual("planning", first["lifecycle_state"])
        self.assertEqual(first["entry_session_id"], second["entry_session_id"])
        self.assertEqual(first["request_fingerprint"], second["request_fingerprint"])
        authority = first["entry_decision"]["entry_session"]["authority_pass"]
        self.assertTrue(authority["planning_mutation_allowed"])
        self.assertFalse(authority["phase_execution_allowed"])

    def test_existing_session_replays_or_conflicts_by_fingerprint(self) -> None:
        original_route = route("model_upgrades_project_to_goal")
        first = run_route(original_route)
        existing = json.dumps(first["entry_decision"]["entry_session"])
        replay = run_route(original_route, "--existing-session-json", existing)
        self.assertTrue(replay["ready"])
        self.assertEqual("replayed_in_progress", replay["idempotency_outcome"])

        changed = dict(original_route)
        changed["objective"] = "A different objective under the same identity."
        conflict = run_route(changed, "--existing-session-json", existing)
        self.assertFalse(conflict["ready"])
        self.assertIn("idempotency_fingerprint_conflict", conflict["blockers"])

    def test_short_reply_reuses_the_active_task_fingerprint(self) -> None:
        original = run_route(route("model_upgrades_project_to_goal"))
        existing = json.dumps(original["entry_decision"]["entry_session"])
        continued = run_route(
            route("short_reply_inherits_route_and_skill"),
            "--existing-session-json",
            existing,
        )
        self.assertTrue(continued["ready"], continued["blockers"])
        self.assertEqual("replayed_in_progress", continued["idempotency_outcome"])
        self.assertEqual(
            original["request_fingerprint"], continued["request_fingerprint"]
        )

    def test_direct_and_compound_routes_cannot_initialize_goal_state(self) -> None:
        for name in ("direct_read_only", "compound_named_skill"):
            with self.subTest(name=name):
                result = run_route(route(name))
                self.assertFalse(result["ready"])
                self.assertIn("entry_route_not_goal_lifecycle", result["blockers"])
                self.assertNotIn("entry_session", result.get("entry_decision", {}))

    def test_resume_requires_goal_context_verified_cursor(self) -> None:
        resume = route("model_upgrades_project_to_goal")
        resume["goal_action"] = "resume"
        resume["resume_cursor"] = {
            "issuer": "goal-context",
            "verification_status": "verified",
            "goal_id": "goal-existing",
            "revision": 4,
            "state_source": "goal-store",
        }
        result = run_route(resume)
        self.assertTrue(result["ready"])
        self.assertEqual("goal-existing", result["goal_id"])

        forged_session = json.loads(
            json.dumps(result["entry_decision"]["entry_session"])
        )
        forged_session["authority_pass"]["cursor"]["goal_id"] = "goal-other"
        forged = run_route(
            resume, "--existing-session-json", json.dumps(forged_session)
        )
        self.assertFalse(forged["ready"])
        self.assertIn("idempotency_cursor_conflict", forged["blockers"])

        resume["resume_cursor"] = dict(resume["resume_cursor"])
        resume["resume_cursor"]["verification_status"] = "caller_asserted"
        rejected = run_route(resume)
        self.assertFalse(rejected["ready"])
        self.assertTrue(
            any("resume_cursor_unverified" in item for item in rejected["blockers"])
        )

    def test_objective_limit_fails_closed(self) -> None:
        oversized = route("model_upgrades_project_to_goal")
        oversized["objective"] = "x" * 4001
        result = run_route(oversized)
        self.assertFalse(result["ready"])
        self.assertTrue(
            any("goal_objective_over_4000" in item for item in result["blockers"])
        )

    def test_legacy_resolver_requires_explicit_flag(self) -> None:
        args = PREFLIGHT.parse_args(
            [
                "--legacy-resolver",
                "--request",
                "Please create a long-running Goal with tests",
                "--readiness-status",
                "passed",
            ]
        )
        result = PREFLIGHT.build_preflight(args)
        self.assertEqual("legacy_resolver", result["route_authority"])


if __name__ == "__main__":
    unittest.main()
