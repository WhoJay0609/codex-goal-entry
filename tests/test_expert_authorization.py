from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import ROOT, authorization, load_script


class ExpertAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_script("authorize_expert_skill.py")
        refs = ROOT / "skills" / "goal-backend" / "references"
        cls.experts = json.loads((refs / "expert-registry.json").read_text())
        cls.families = json.loads((refs / "skill-family-registry.json").read_text())

    def test_registry_has_exactly_nine_experts(self) -> None:
        self.assertEqual(9, len(self.experts["experts"]))
        self.assertEqual(
            {
                "implementation",
                "debugging",
                "test_and_verification",
                "architecture_and_code_review",
                "research_and_experiment",
                "documentation_and_communication",
                "release_and_reliability",
                "security_and_risk",
                "frontend_and_ui_engineering",
            },
            {item["id"] for item in self.experts["experts"]},
        )

    def test_registered_family_member_is_allowed(self) -> None:
        result = self.module.authorize_expert_skill(
            "implementation",
            "implement",
            self.experts,
            self.families,
        )
        self.assertTrue(result["allowed"])

        compound = self.module.authorize_expert_skill(
            "debugging",
            "compound-engineering:ce-debug",
            self.experts,
            self.families,
        )
        self.assertTrue(compound["allowed"])

    def test_unknown_and_wrong_family_skills_are_denied(self) -> None:
        unknown = self.module.authorize_expert_skill(
            "implementation",
            "brand-new-unregistered-skill",
            self.experts,
            self.families,
        )
        wrong = self.module.authorize_expert_skill(
            "documentation_and_communication", "implement", self.experts, self.families
        )
        self.assertFalse(unknown["allowed"])
        self.assertFalse(wrong["allowed"])

    def test_global_deny_wins_even_if_fixture_adds_membership(self) -> None:
        families = json.loads(json.dumps(self.families))
        families["families"]["implementation"]["skills"].append("goal-backend")
        result = self.module.authorize_expert_skill(
            "implementation", "goal-backend", self.experts, families
        )
        self.assertFalse(result["allowed"])
        self.assertEqual("global_deny", result["reason"])

        families["families"]["implementation"]["skills"].append(
            "compound-engineering:ce-work"
        )
        orchestrator = self.module.authorize_expert_skill(
            "implementation",
            "compound-engineering:ce-work",
            self.experts,
            families,
        )
        self.assertFalse(orchestrator["allowed"])
        self.assertEqual("global_deny", orchestrator["reason"])

    def test_permission_decision_is_recorded_through_authorized_evidence(self) -> None:
        init = load_script("init_goal_run.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            init.initialize_run(authorization(), run_dir)
            result = self.module.authorize_and_record_expert_skill(
                authorization("goal-team", "evidence.record"),
                run_dir,
                "documentation_and_communication",
                "implement",
                self.experts,
                self.families,
            )
            self.assertFalse(result["allowed"])
            self.assertTrue(result["evidence_recorded"])
            row = json.loads((run_dir / "events.jsonl").read_text().splitlines()[0])
            self.assertEqual("expert_skill_authorization", row["kind"])
            self.assertEqual("blocked", row["status"])

    def test_invalid_permission_caller_produces_no_artifact(self) -> None:
        init = load_script("init_goal_run.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            init.initialize_run(authorization(), run_dir)
            result = self.module.authorize_and_record_expert_skill(
                authorization("goal-team", "evidence.record", actor="user"),
                run_dir,
                "implementation",
                "implement",
                self.experts,
                self.families,
            )
            self.assertFalse(result["allowed"])
            self.assertFalse(result["evidence_recorded"])
            self.assertFalse((run_dir / "events.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
