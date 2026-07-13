from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from support import authorization, load_script


class BackendAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.auth = load_script("authorize_backend_call.py")

    def test_valid_owner_capability_pairs(self) -> None:
        pairs = {
            "run.initialize": {"goal-context", "goal-dispatch"},
            "evidence.record": {"goal-context", "goal-dispatch", "goal-team"},
            "trace.validate": {"goal-trace", "goal-close"},
            "runtime.cleanup": {"goal-close"},
            "goal.sync": {"goal-close"},
            "trace.read_legacy": {"goal-trace"},
        }
        for capability, owners in pairs.items():
            for owner in owners:
                with self.subTest(capability=capability, owner=owner):
                    result = self.auth.authorize(authorization(owner, capability))
                    self.assertTrue(result["allowed"])

    def test_invalid_callers_fail_closed(self) -> None:
        cases = [
            authorization(actor="user"),
            authorization(actor="compound_engineering"),
            authorization(actor="subagent"),
            authorization(ready=False),
            authorization("goal-team", "evidence.record", execution_allowed=False),
            authorization("goal-close", "run.initialize"),
            authorization("goal-dispatch", "unknown.capability"),
        ]
        missing_session = authorization()
        del missing_session["entry_decision"]["entry_session"]
        cases.append(missing_session)
        mismatch = authorization()
        mismatch["goal_preflight"]["entry_session_id"] = "entry-other"
        cases.append(mismatch)

        for request in cases:
            with self.subTest(request=request):
                result = self.auth.authorize(request)
                self.assertFalse(result["allowed"])
                self.assertTrue(result["reasons"])

    def test_planning_authority_does_not_grant_unit_execution(self) -> None:
        planning = authorization(
            "goal-context", "run.initialize", execution_allowed=False
        )
        planning["operation_phase"] = "planning"
        self.assertTrue(self.auth.authorize(planning)["allowed"])

        execution = authorization(
            "goal-team", "evidence.record", execution_allowed=False
        )
        execution["operation_phase"] = "active"
        result = self.auth.authorize(execution)
        self.assertFalse(result["allowed"])
        self.assertIn("phase_execution_not_allowed", result["reasons"])

    def test_denial_does_not_create_artifacts(self) -> None:
        init = load_script("init_goal_run.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            result = init.initialize_run(authorization(actor="user"), run_dir)
            self.assertFalse(result["ok"])
            self.assertFalse(run_dir.exists())

    def test_fingerprint_must_be_well_formed_and_linked(self) -> None:
        request = copy.deepcopy(authorization())
        request["entry_decision"]["request_fingerprint"] = "not-a-digest"
        result = self.auth.authorize(request)
        self.assertFalse(result["allowed"])
        self.assertIn("request_fingerprint_invalid", result["reasons"])

    def test_model_route_scope_is_cryptographically_bound_to_session(self) -> None:
        changed_digest = copy.deepcopy(authorization())
        changed_digest["entry_decision"]["entry_session"][
            "authorization_scope_digest"
        ] = "b" * 64
        result = self.auth.authorize(changed_digest)
        self.assertFalse(result["allowed"])
        self.assertIn("authorization_scope_digest_mismatch", result["reasons"])

        widened_authority = copy.deepcopy(authorization())
        widened_authority["entry_decision"]["entry_session"]["authority_pass"][
            "external_actions"
        ] = ["pr.create"]
        result = self.auth.authorize(widened_authority)
        self.assertFalse(result["allowed"])
        self.assertIn("authority_external_actions_mismatch", result["reasons"])

    def test_resume_cursor_is_bound_to_model_route(self) -> None:
        request = copy.deepcopy(authorization())
        cursor = {
            "issuer": "goal-context",
            "verification_status": "verified",
            "goal_id": "goal-123",
            "revision": 2,
            "state_source": "goal-store",
        }
        request["entry_decision"]["model_route"].update(
            {"goal_action": "resume", "resume_cursor": cursor}
        )
        request["entry_decision"]["entry_session"]["authority_pass"][
            "cursor"
        ] = dict(cursor)
        self.assertTrue(self.auth.authorize(request)["allowed"])
        request["entry_decision"]["entry_session"]["authority_pass"]["cursor"][
            "goal_id"
        ] = "goal-other"
        result = self.auth.authorize(request)
        self.assertFalse(result["allowed"])
        self.assertIn("authority_resume_cursor_mismatch", result["reasons"])


if __name__ == "__main__":
    unittest.main()
