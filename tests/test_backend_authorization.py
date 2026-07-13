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
            authorization(execution_allowed=False),
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


if __name__ == "__main__":
    unittest.main()
