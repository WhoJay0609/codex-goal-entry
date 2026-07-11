from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def load_resolver():
    path = ROOT / "scripts" / "resolve_goal_entry.py"
    spec = importlib.util.spec_from_file_location("goal_entry_resolver_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["goal_entry_resolver_tests"] = module
    spec.loader.exec_module(module)
    return module


RESOLVER = load_resolver()


def args(request: str, **overrides):
    values = {
        "request": request,
        "request_file": None,
        "active_goal_json": None,
        "runtime_state_json": None,
        "capabilities_json": None,
        "readiness_status": "passed",
        "superpowers_available": "true",
        "direct_runtime_requested": False,
        "objective": None,
        "objective_file": None,
        "conversation_mode": "default",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ResolverContractTests(unittest.TestCase):
    def test_declarative_routing_cases(self) -> None:
        cases = json.loads((FIXTURES / "routing_cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                decision = RESOLVER.resolve(args(case["request"]))
                contract = decision["decision_contract"]
                expected = case["expected"]
                if "request_mode" in expected:
                    self.assertEqual(expected["request_mode"], decision["request_mode"])
                self.assertEqual(expected["task_profile"], contract["task_profile"])
                self.assertEqual(expected["lifecycle_state"], contract["lifecycle_state"])

    def test_declarative_capability_cases(self) -> None:
        cases = json.loads((FIXTURES / "capability_cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                decision = RESOLVER.resolve(
                    args(case["request"], capabilities_json={"capabilities": case["capabilities"]})
                )
                contract = decision["decision_contract"]
                self.assertEqual(case["expected_provider_status"], contract["provider_status"])
                self.assertEqual(case["expected_authorization_state"], contract["authorization_state"])

    def test_legacy_fields_remain_compatible(self) -> None:
        decision = RESOLVER.resolve(args("PLEASE IMPLEMENT THIS PLAN with tests"))
        self.assertEqual("execute_goal", decision["request_mode"])
        self.assertEqual("standard_superpowers", decision["goal_entry_tier"])
        self.assertEqual("create_goal", decision["goal_action"])
        self.assertEqual("passed", decision["readiness_gate"]["status"])
        self.assertEqual(1, decision["version"])
        self.assertEqual(2, decision["decision_contract"]["version"])

    def test_bilingual_engineering_requests_share_profile_and_lifecycle(self) -> None:
        english = RESOLVER.resolve(args("Please implement this cross-module engineering project with milestone acceptance"))
        chinese = RESOLVER.resolve(args("请实现这个跨模块工程，并按里程碑独立验收"))
        for decision in (english, chinese):
            contract = decision["decision_contract"]
            self.assertEqual("complex_engineering", contract["task_profile"])
            self.assertEqual("roadmap_required", contract["lifecycle_state"])

    def test_bilingual_research_requests_share_profile_despite_analysis_terms(self) -> None:
        english = RESOLVER.resolve(args("Start autoresearch, analyze evidence, iterate experiments, and implement the paper method"))
        chinese = RESOLVER.resolve(args("请启动自动科研，分析证据、迭代实验并实现论文方法"))
        for decision in (english, chinese):
            self.assertEqual("execute_goal", decision["request_mode"])
            self.assertEqual("scientific_autoresearch", decision["decision_contract"]["task_profile"])

    def test_explicit_no_execution_remains_a_hard_veto(self) -> None:
        decision = RESOLVER.resolve(args("请分析自动科研和实验实现方案，但不要执行"))
        self.assertNotEqual("execute_goal", decision["request_mode"])
        contract = decision["decision_contract"]
        self.assertIsNone(contract["task_profile"])
        self.assertEqual("not_applicable", contract["lifecycle_state"])
        self.assertEqual("not_required", contract["authorization_state"])

    def test_explicit_no_execution_cannot_bind_an_active_goal(self) -> None:
        decision = RESOLVER.resolve(args("继续，但不要执行", active_goal_json={"status": "active"}))
        self.assertEqual("report_only", decision["request_mode"])
        self.assertEqual("none", decision["goal_action"])
        self.assertEqual("not_applicable", decision["decision_contract"]["lifecycle_state"])

    def test_conflicting_authority_records_require_state_resolution(self) -> None:
        runtime_state = {
            "goal": {"id": "goal-a", "status": "active"},
            "roadmap": {"goal_id": "goal-a", "status": "approved"},
            "accepted_milestone": {"goal_id": "goal-b", "id": "m1", "status": "accepted"},
        }
        decision = RESOLVER.resolve(args("继续执行", runtime_state_json=runtime_state))
        contract = decision["decision_contract"]
        self.assertEqual("state_required", contract["lifecycle_state"])
        self.assertEqual("state_required", contract["authorization_state"])
        self.assertEqual("fallback_handoff", decision["goal_action"])
        self.assertEqual("goal-context", contract["next_owner"])

    def test_approved_roadmap_is_milestone_ready(self) -> None:
        runtime_state = {
            "goal": {"id": "goal-a", "status": "active"},
            "roadmap": {"goal_id": "goal-a", "status": "approved"},
        }
        required = RESOLVER.RUNTIME_PROFILES["complex_engineering"]["required_capabilities"]
        decision = RESOLVER.resolve(
            args(
                "请继续实现",
                active_goal_json={"status": "active"},
                runtime_state_json=runtime_state,
                capabilities_json={"capabilities": required},
            )
        )
        contract = decision["decision_contract"]
        self.assertEqual("milestone_ready", contract["lifecycle_state"])
        self.assertEqual("authorized", contract["authorization_state"])

    def test_durable_goal_without_active_binding_requires_resume_handoff(self) -> None:
        runtime_state = {
            "goal": {"id": "goal-a", "status": "active"},
            "roadmap": {"goal_id": "goal-a", "status": "approved"},
        }
        decision = RESOLVER.resolve(args("继续执行", runtime_state_json=runtime_state))
        contract = decision["decision_contract"]
        self.assertEqual("resume_required", contract["lifecycle_state"])
        self.assertEqual("handoff_required", contract["authorization_state"])
        self.assertEqual("fallback_handoff", decision["goal_action"])
        self.assertEqual("goal-context", contract["next_owner"])

    def test_malformed_durable_subrecords_fail_closed(self) -> None:
        invalid_states = [
            {"goal": "goal-a"},
            {"goal": {"id": "goal-a", "status": "unknown"}},
            {
                "goal": {"id": "goal-a", "status": "active"},
                "roadmap": {"status": "approved"},
            },
            {
                "goal": {"id": "goal-a", "status": "active"},
                "active_work": ["not-an-object"],
            },
        ]
        for runtime_state in invalid_states:
            with self.subTest(runtime_state=runtime_state):
                with self.assertRaises(ValueError):
                    RESOLVER.resolve(args("继续执行", runtime_state_json=runtime_state))

    def test_missing_capabilities_degrade_without_changing_profile(self) -> None:
        decision = RESOLVER.resolve(args("请实现这个跨模块工程", capabilities_json={"capabilities": ["goal-preflight"]}))
        contract = decision["decision_contract"]
        self.assertEqual("complex_engineering", contract["task_profile"])
        self.assertEqual("roadmap_required", contract["lifecycle_state"])
        self.assertEqual("degraded", contract["provider_status"])
        self.assertEqual("handoff_required", contract["authorization_state"])
        self.assertIn("goal-plan", contract["missing_capabilities"])

    def test_complete_capabilities_report_full_stack(self) -> None:
        required = RESOLVER.RUNTIME_PROFILES["complex_engineering"]["required_capabilities"]
        decision = RESOLVER.resolve(args("请实现这个跨模块工程", capabilities_json={"capabilities": required}))
        contract = decision["decision_contract"]
        self.assertEqual("full_stack", contract["provider_status"])
        self.assertEqual([], contract["missing_capabilities"])

    def test_unknown_capability_is_incompatible(self) -> None:
        decision = RESOLVER.resolve(args("请实现这个跨模块工程", capabilities_json={"capabilities": ["unknown-owner"]}))
        contract = decision["decision_contract"]
        self.assertEqual("incompatible", contract["provider_status"])
        self.assertEqual(["unknown-owner"], contract["unknown_capabilities"])


if __name__ == "__main__":
    unittest.main()
