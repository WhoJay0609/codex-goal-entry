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
        "request_parts_json": None,
        "clarification_json": None,
        "idempotency_key": None,
        "prior_entry_session_json": None,
        "goal_cursor_json": None,
        "active_goals_json": None,
        "expected_goal_revision": None,
        "conversation_correlation": None,
        "provider_attestations_json": None,
        "active_phase_id": None,
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
        self.assertEqual("handoff_required", contract["authorization_state"])
        self.assertEqual("blocked", decision["entry_session"]["authority_pass"]["status"])

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

    def test_entry_session_is_additive_to_legacy_projections(self) -> None:
        decision = RESOLVER.resolve(args("PLEASE IMPLEMENT THIS PLAN with tests"))
        self.assertEqual(1, decision["version"])
        self.assertEqual(2, decision["decision_contract"]["version"])
        self.assertEqual("resolved", decision["entry_session"]["semantic_pass"]["status"])

    def test_quoted_mutation_cannot_override_read_only_instruction(self) -> None:
        parts = {
            "instruction": "只分析风险，不要执行",
            "quoted": "PLEASE IMPLEMENT THIS PLAN",
            "attachments": ["implement everything"],
            "prior_assistant": "create a goal now",
        }
        decision = RESOLVER.resolve(args("", request_parts_json=parts))
        session = decision["entry_session"]
        self.assertFalse(session["semantic_pass"]["mutation_candidate"])
        self.assertEqual("not_required", session["authority_pass"]["status"])
        self.assertEqual(["instruction"], session["semantic_pass"]["provenance"]["authoritative_lanes"])

    def test_ambiguous_mutation_gets_one_clarification_then_abstains(self) -> None:
        first = RESOLVER.resolve(args("review or implement this plan"))["entry_session"]
        self.assertEqual("clarification_required", first["semantic_pass"]["status"])
        self.assertFalse(first["authority_pass"]["goal_mutation_allowed"])
        second = RESOLVER.resolve(args(
            "review or implement this plan",
            clarification_json={"attempt": 1, "instruction": "still review or implement it"},
        ))["entry_session"]
        self.assertEqual("unresolved_non_mutating", second["semantic_pass"]["status"])

    def test_no_execution_composite_returns_preview_only_phase_graph(self) -> None:
        session = RESOLVER.resolve(args("先调研，再实现，最后跑实验，但不要执行"))["entry_session"]
        semantic = session["semantic_pass"]
        self.assertTrue(semantic["preview_only"])
        self.assertFalse(semantic["mutation_candidate"])
        self.assertGreaterEqual(len(semantic["phase_graph"]), 2)
        self.assertEqual("not_required", session["authority_pass"]["status"])

    def test_explicit_phase_order_and_adjacent_profile_collapse(self) -> None:
        cases = json.loads((FIXTURES / "composite_phase_cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                phases = RESOLVER.resolve(args(case["request"]))["entry_session"]["semantic_pass"]["phase_graph"]
                self.assertEqual(case["profiles"], [phase["runtime_profile"] for phase in phases])

    def test_replay_is_stable_and_mismatched_fingerprint_conflicts(self) -> None:
        first = RESOLVER.resolve(args("请实现解析器", idempotency_key="client-1"))["entry_session"]
        prior = dict(first)
        prior["status"] = "complete"
        replay = RESOLVER.resolve(args(
            "请实现解析器", idempotency_key="client-1", prior_entry_session_json=prior
        ))["entry_session"]
        self.assertEqual(first["session_id"], replay["session_id"])
        self.assertEqual("replayed_completed", replay["idempotency"]["status"])
        conflict = RESOLVER.resolve(args(
            "请实现别的功能", idempotency_key="client-1", prior_entry_session_json=prior
        ))["entry_session"]
        self.assertEqual("conflict", conflict["idempotency"]["status"])
        self.assertFalse(conflict["authority_pass"]["goal_mutation_allowed"])

    def test_replay_does_not_extend_expired_cursor_authority(self) -> None:
        cursor = json.loads((FIXTURES / "cursor_cases.json").read_text(encoding="utf-8"))[0]["cursor"]
        first = RESOLVER.resolve(args(
            "继续执行", active_goal_json={"status": "active"}, goal_cursor_json=cursor,
            idempotency_key="resume-1",
        ))["entry_session"]
        prior = dict(first, status="complete")
        expired = dict(cursor, expires_at="2020-01-01T00:00:00Z")
        replay = RESOLVER.resolve(args(
            "继续执行", active_goal_json={"status": "active"}, goal_cursor_json=expired,
            idempotency_key="resume-1", prior_entry_session_json=prior,
        ))["entry_session"]
        self.assertEqual("replayed_completed", replay["idempotency"]["status"])
        self.assertEqual("blocked", replay["authority_pass"]["status"])
        self.assertIn("expired_goal_cursor", replay["authority_pass"]["reasons"])

    def test_verified_cursor_binds_and_stale_revision_blocks(self) -> None:
        cursor = json.loads((FIXTURES / "cursor_cases.json").read_text(encoding="utf-8"))[0]["cursor"]
        bound = RESOLVER.resolve(args(
            "继续执行", active_goal_json={"status": "active"}, goal_cursor_json=cursor,
            expected_goal_revision=3,
        ))["entry_session"]
        self.assertEqual("g-1", bound["authority_pass"]["cursor"]["goal_id"])
        stale = RESOLVER.resolve(args(
            "继续执行", active_goal_json={"status": "active"}, goal_cursor_json=cursor,
            expected_goal_revision=2,
        ))["entry_session"]
        self.assertEqual("blocked", stale["authority_pass"]["status"])
        self.assertIn("stale_goal_revision", stale["authority_pass"]["reasons"])

    def test_multiple_cursor_candidates_require_selection_and_recency_only_sorts(self) -> None:
        base = json.loads((FIXTURES / "cursor_cases.json").read_text(encoding="utf-8"))[0]["cursor"]
        other = dict(base, goal_id="g-2", proof_ref="proof:g-2:r4", revision=4,
                     conversation_correlation="thread-2", issued_at="2026-07-11T01:00:00Z")
        authority = RESOLVER.resolve(args(
            "继续执行", active_goal_json={"status": "active"}, active_goals_json=[base, other]
        ))["entry_session"]["authority_pass"]
        self.assertEqual("goal_selection_required", authority["status"])
        self.assertEqual(["g-2", "g-1"], [item["goal_id"] for item in authority["goal_candidates"]])

    def test_one_exact_correlation_match_binds_automatically(self) -> None:
        base = json.loads((FIXTURES / "cursor_cases.json").read_text(encoding="utf-8"))[0]["cursor"]
        other = dict(base, goal_id="g-2", proof_ref="proof:g-2:r4", revision=4,
                     conversation_correlation="thread-2")
        authority = RESOLVER.resolve(args(
            "继续执行", active_goal_json={"status": "active"}, active_goals_json=[base, other],
            conversation_correlation="thread-1",
        ))["entry_session"]["authority_pass"]
        self.assertEqual("g-1", authority["cursor"]["goal_id"])

    def test_spoofed_caller_cursor_cannot_authorize_binding(self) -> None:
        spoofed = {
            "issuer": "caller", "verification_status": "verified", "proof_ref": "self-asserted",
            "goal_id": "g", "revision": 1, "status": "active",
        }
        decision = RESOLVER.resolve(args(
            "继续执行", active_goal_json={"status": "active"}, goal_cursor_json=spoofed,
        ))
        self.assertEqual("blocked", decision["entry_session"]["authority_pass"]["status"])
        self.assertEqual("fallback_handoff", decision["goal_action"])

    def test_declarations_do_not_authorize_provider_but_attestation_does(self) -> None:
        required = RESOLVER.RUNTIME_PROFILES["complex_engineering"]["required_capabilities"]
        declared = RESOLVER.resolve(args(
            "请实现这个跨模块工程", capabilities_json={"capabilities": required}
        ))["entry_session"]["authority_pass"]
        self.assertFalse(declared["phase_execution_allowed"])
        attestation = json.loads((FIXTURES / "attestation_cases.json").read_text(encoding="utf-8"))[0]["attestation"]
        probe = RESOLVER.resolve(args("请实现这个跨模块工程"))["entry_session"]
        attestation["request_fingerprint"] = probe["request_fingerprint"]
        ready = RESOLVER.resolve(args(
            "请实现这个跨模块工程", provider_attestations_json=[attestation]
        ))["entry_session"]["authority_pass"]
        self.assertTrue(ready["phase_execution_allowed"])

    def test_spoofed_or_unhealthy_attestation_blocks_phase_not_goal_creation(self) -> None:
        attestation = json.loads((FIXTURES / "attestation_cases.json").read_text(encoding="utf-8"))[0]["attestation"]
        probe = RESOLVER.resolve(args("请实现这个跨模块工程"))["entry_session"]
        attestation["request_fingerprint"] = probe["request_fingerprint"]
        for invalid in (dict(attestation, issuer="caller"), dict(attestation, health="unhealthy")):
            with self.subTest(invalid=invalid):
                authority = RESOLVER.resolve(args(
                    "请实现这个跨模块工程", provider_attestations_json=[invalid]
                ))["entry_session"]["authority_pass"]
                self.assertTrue(authority["goal_mutation_allowed"])
                self.assertFalse(authority["phase_execution_allowed"])


if __name__ == "__main__":
    unittest.main()
