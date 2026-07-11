#!/usr/bin/env python3
"""Resolve harness-agent-for-goal request mode, tier, and dispatch route."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime_profiles.json"
RUNTIME_CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
ENTRY_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "references" / "entry_session_contract.json"
ENTRY_CONTRACT = json.loads(ENTRY_CONTRACT_PATH.read_text(encoding="utf-8"))
RUNTIME_PROFILES = RUNTIME_CONTRACT["profiles"]
KNOWN_CAPABILITIES = set(RUNTIME_CONTRACT["capabilities"])

REQUEST_MODES = {
    "report_only",
    "plan_only",
    "copy_only_handoff",
    "advisory_debate",
    "execute_goal",
    "active_goal_bind",
}
GOAL_ENTRY_TIERS = {
    "quick_single_agent",
    "standard_superpowers",
    "full_autonomous",
}
SUPERPOWERS_DISPATCH_LEVELS = {
    "intent_only",
    "minimal_dispatch",
    "full_dispatch",
}
SUBAGENT_EXECUTION_MODES = {
    "single_agent_exception",
    "superpowers_subagents",
    "runtime_subagents",
    "inline_expert_memos",
}
READINESS_STATUSES = {
    "auto",
    "not_required",
    "pending",
    "passed",
    "blocked",
}


@dataclass(frozen=True)
class PatternRule:
    name: str
    pattern: re.Pattern[str]


EXECUTION_RULES = [
    PatternRule(
        "explicit_autoresearch_execution",
        re.compile(
            r"(start|launch|run|begin|启动|开展|进行).{0,40}"
            r"(auto[- ]?research|research loop|experiment loop|自动科研|科研循环|实验迭代)",
            re.I,
        ),
    ),
    PatternRule("explicit_please_implement", re.compile(r"\bPLEASE IMPLEMENT THIS PLAN\b", re.I)),
    PatternRule("explicit_implement_this_plan", re.compile(r"\bimplement this plan\b", re.I)),
    PatternRule("explicit_start_execution", re.compile(r"\b(start|begin|proceed with)\s+(execution|implementation)\b", re.I)),
    PatternRule("explicit_do_it", re.compile(r"\bdo it\b", re.I)),
    PatternRule(
        "explicit_english_task_assignment",
        re.compile(
            r"\b(please|can you|could you|help me|make|update|fix|add|remove|build|ship|implement|create)"
            r".{0,80}\b(fix|update|add|remove|build|ship|implement|create|generate|validate|test|wire|refactor)\b",
            re.I,
        ),
    ),
    PatternRule(
        "explicit_goal_trigger_maintenance",
        re.compile(
            r"((auto(?:matically)?\s+(set|create|trigger).{0,40}goal|goal.{0,40}auto(?:matically)?\s+(set|create|trigger))"
            r"|((make|让|使).{0,80}(goal|目标).{0,40}(easier to trigger|更容易触发|自动设置|自动创建|设置)))",
            re.I,
        ),
    ),
    PatternRule("explicit_chinese_execute", re.compile(r"(执行|实现|开始做|开始执行|继续执行)")),
    PatternRule(
        "explicit_chinese_research_execution",
        re.compile(r"(请|帮我|需要你|我要你).{0,40}(启动|开展|进行).{0,20}(自动科研|科研|实验迭代)"),
    ),
    PatternRule(
        "explicit_chinese_task_assignment",
        re.compile(
            r"(请|帮我|帮忙|你来|麻烦|需要你|我要你|替我).{0,60}"
            r"(修复|修一下|修改|改成|改为|实现|新增|添加|删除|更新|增强|整理|重构|迁移|接入|配置|安装|生成|创建|跑|验证|测试|提交|推送|落地|完成|做完|处理)"
        ),
    ),
    PatternRule(
        "explicit_chinese_object_mutation",
        re.compile(
            r"(把|将).{1,100}"
            r"(改成|改为|修复|更新|增强|迁移|接入|整理|重构|删除|新增|添加|生成|创建|纳入git|提交|推送)"
        ),
    ),
    PatternRule(
        "explicit_chinese_team_execution",
        re.compile(
            r"(组建团队|组建[^，。；\n]{0,12}团队|子代理|subagents?).{0,120}"
            r"(执行|实现|开始做|修复|更新|增强|整理|修改|改写|构建|落地|跑|验证|推送|提交|生成|创建)"
        ),
    ),
    PatternRule(
        "explicit_chinese_write_maintenance",
        re.compile(
            r"(进行更新|进行增强|更新一下|增强|修复|修改|改写|整理).{0,120}"
            r"(skill|skills|文件|代码|仓库|repo|项目|论文|方法)"
        ),
    ),
]
NO_EXECUTION_PATTERN = re.compile(
    r"(不要执行|不执行|先不要执行|不要开始执行|不要实现|不实现|do not execute|do not implement|no execution)",
    re.I,
)
REPORT_RULES = [
    PatternRule("report_status", re.compile(r"\b(status|summari[sz]e|explain|analysis|analy[sz]e)\b", re.I)),
    PatternRule("report_review", re.compile(r"\b(review|audit|critique|recommendation|recommendations)\b", re.I)),
    PatternRule("report_chinese_review", re.compile(r"(审视|评估|评价|分析|缺点|问题|建议|如何改进)")),
]
PLAN_RULES = [
    PatternRule("plan_terms", re.compile(r"\b(plan|proposal|design|options|strategy|roadmap)\b", re.I)),
    PatternRule("plan_no_write", re.compile(r"\b(no[- ]?write|planning[- ]only|do not implement)\b", re.I)),
    PatternRule("plan_chinese_terms", re.compile(r"(计划|规划|只规划|不要执行|不安装|不写文件)")),
]
HANDOFF_RULES = [
    PatternRule("handoff_goal", re.compile(r"(^|\s)/goal\b", re.I)),
    PatternRule("handoff_terms", re.compile(r"\b(handoff|copyable|continuation package)\b", re.I)),
    PatternRule("handoff_chinese_terms", re.compile(r"(交接|可复制|继续包)")),
]
ADVISORY_RULES = [
    PatternRule("advisory_experts", re.compile(r"(组建专家讨论|组建专家团队讨论|专家评审|讨论方案|先讨论)")),
    PatternRule("advisory_terms", re.compile(r"\b(advisory debate|expert discussion|expert review)\b", re.I)),
]
ACTIVE_GOAL_RULES = [
    PatternRule("active_continue", re.compile(r"\b(continue|resume|carry on)\b", re.I)),
    PatternRule("active_chinese_continue", re.compile(r"(继续|恢复)")),
]
FULL_TIER_RULES = [
    PatternRule("full_high_risk", re.compile(r"\b(high[- ]risk|long[- ]running|multi[- ]branch|cross[- ]module)\b", re.I)),
    PatternRule("full_audit", re.compile(r"\b(independent audit|evidence[- ]sensitive|paper[- ]sensitive)\b", re.I)),
    PatternRule("full_chinese", re.compile(r"(高风险|长时间|多分支|跨模块|论文|证据|独立审计|完整自治)")),
]
QUICK_TIER_RULES = [
    PatternRule("quick_tiny", re.compile(r"\b(tiny|trivial|one[- ]command|simple read[- ]only|quick check)\b", re.I)),
    PatternRule("quick_chinese", re.compile(r"(很小|简单检查|只读检查|一个命令)")),
]
DEBUG_ROUTE_RULES = [
    PatternRule("route_debug", re.compile(r"\b(debug|bug|failure|regression|root cause|fix ci)\b", re.I)),
    PatternRule("route_chinese_debug", re.compile(r"(调试|故障|失败|回归|根因|修复 CI)")),
]
TEST_ROUTE_RULES = [
    PatternRule("route_test", re.compile(r"\b(test[- ]first|tdd|unit test|pytest|regression test)\b", re.I)),
    PatternRule("route_chinese_test", re.compile(r"(测试优先|单元测试|回归测试)")),
]
REVIEW_ROUTE_RULES = [
    PatternRule("route_review", re.compile(r"\b(code review|review|finish|release|closeout)\b", re.I)),
    PatternRule("route_chinese_review", re.compile(r"(代码审查|收尾|发布|验收)")),
]
PARALLEL_ROUTE_RULES = [
    PatternRule("route_parallel", re.compile(r"\b(parallel|independent branches|fan[- ]out|multi[- ]branch)\b", re.I)),
    PatternRule("route_chinese_parallel", re.compile(r"(并行|独立分支|多分支|组建团队|子代理)")),
]
PLAN_ROUTE_RULES = [
    PatternRule("route_plan", re.compile(r"\b(plan|planning|design|architecture|proposal)\b", re.I)),
    PatternRule("route_chinese_plan", re.compile(r"(计划|规划|方案|架构|设计)")),
]
RESEARCH_PROFILE_RULES = [
    PatternRule(
        "profile_autoresearch",
        re.compile(r"(auto[- ]?research|scientific research|research loop|自动科研|科研循环)", re.I),
    ),
    PatternRule(
        "profile_experiment_iteration",
        re.compile(r"(iterate experiments?|experiment iteration|experiment loop|迭代实验|实验迭代|实验循环)", re.I),
    ),
    PatternRule(
        "profile_research_evidence",
        re.compile(r"(hypothesis|claim evidence|paper method|evidence synthesis|研究假设|论文方法|科研证据|证据综合)", re.I),
    ),
]
EXPLICIT_PLANNING_PATTERN = re.compile(r"\b(plan|proposal|design|options|strategy|roadmap)\b|(计划|规划|只规划)", re.I)
AMBIGUOUS_MUTATION_PATTERN = re.compile(
    r"\b(review|analy[sz]e|plan)\s+or\s+(implement|execute|ship|build)\b"
    r"|\b(implement|execute|ship|build)\s+or\s+(review|analy[sz]e|plan)\b"
    r"|(分析|评审|规划).{0,12}(还是|或者).{0,12}(执行|实现|落地)"
    r"|(执行|实现|落地).{0,12}(还是|或者).{0,12}(分析|评审|规划)",
    re.I,
)
PHASE_SEPARATOR_PATTERN = re.compile(
    r"\s*(?:,?\s*\bthen\b|,?\s*\bnext\b|,?\s*\bfinally\b|[，,；;]?\s*(?:然后|再|最后|之后))\s*",
    re.I,
)
PHASE_PREFIX_PATTERN = re.compile(r"^\s*(?:先|first(?:ly)?\b)\s*", re.I)
RESEARCH_PHASE_PATTERN = re.compile(
    r"(auto[- ]?research|research|hypothesis|paper|experiment|evidence|调研|研究|科研|实验|论文|证据)",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text_arg(value: str | None, file_value: str | None) -> str:
    if value and file_value:
        raise SystemExit("pass either inline text or a file path, not both")
    if file_value:
        return Path(file_value).read_text(encoding="utf-8")
    return value or ""


def load_json_arg(value: Any) -> Any:
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise ValueError("JSON input must be an object, array, path, or JSON string")
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize_request_parts(request_text: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {"instruction": request_text, "quoted": "", "attachments": [], "prior_assistant": ""}
    if not isinstance(value, dict):
        raise ValueError("request parts must be a JSON object")
    attachments = value.get("attachments", [])
    if isinstance(attachments, str):
        attachments = [attachments]
    if not isinstance(attachments, list) or not all(isinstance(item, str) for item in attachments):
        raise ValueError("request parts attachments must be an array of strings")
    return {
        "instruction": str(value.get("instruction", request_text)),
        "quoted": str(value.get("quoted", "")),
        "attachments": attachments,
        "prior_assistant": str(value.get("prior_assistant", "")),
    }


def compile_phase_graph(text: str) -> list[dict[str, Any]]:
    clean = NO_EXECUTION_PATTERN.sub("", text)
    clauses = [PHASE_PREFIX_PATTERN.sub("", item).strip(" ，,；;") for item in PHASE_SEPARATOR_PATTERN.split(clean)]
    clauses = [item for item in clauses if item]
    if not clauses:
        clauses = [clean.strip() or text.strip() or "request"]
    grouped: list[dict[str, Any]] = []
    for clause in clauses:
        profile = "scientific_autoresearch" if RESEARCH_PHASE_PATTERN.search(clause) else "complex_engineering"
        if grouped and grouped[-1]["runtime_profile"] == profile:
            grouped[-1]["outcome"] = f'{grouped[-1]["outcome"]}; {clause}'
            continue
        grouped.append({"runtime_profile": profile, "outcome": clause})
    phases: list[dict[str, Any]] = []
    for index, item in enumerate(grouped, start=1):
        phase_id = f"phase-{index}"
        profile = item["runtime_profile"]
        phases.append({
            "phase_id": phase_id,
            "runtime_profile": profile,
            "outcome": item["outcome"],
            "artifacts": list(RUNTIME_PROFILES[profile]["evidence_expectations"]),
            "dependencies": [] if index == 1 else [f"phase-{index - 1}"],
            "entry_condition": "session_authority_ready" if index == 1 else "dependencies_accepted",
            "exit_condition": "profile_evidence_satisfied",
        })
    return phases


def build_semantic_pass(instruction: str, request_mode: str, clarification: Any) -> dict[str, Any]:
    if clarification is not None and not isinstance(clarification, dict):
        raise ValueError("clarification must be a JSON object")
    effective = str((clarification or {}).get("instruction", instruction))
    ambiguous = bool(AMBIGUOUS_MUTATION_PATTERN.search(effective))
    attempt = int((clarification or {}).get("attempt", 0))
    if ambiguous and attempt == 0:
        status = "clarification_required"
    elif ambiguous:
        status = "unresolved_non_mutating"
    else:
        status = "resolved"
    mutation_candidate = status == "resolved" and request_mode in {"execute_goal", "active_goal_bind"}
    phase_graph = compile_phase_graph(effective)
    preview_only = not mutation_candidate and len(phase_graph) > 1
    return {
        "status": status,
        "instruction": effective,
        "intent": request_mode,
        "mutation_candidate": mutation_candidate,
        "preview_only": preview_only,
        "phase_graph": phase_graph,
        "provenance": {
            "authoritative_lanes": ["instruction"],
            "context_only_lanes": ["quoted", "attachments", "prior_assistant"],
        },
        "clarification": (
            {"attempt": 1, "question": "Should I only analyze/review this request, or execute the mutation?"}
            if status == "clarification_required"
            else None
        ),
        "interpretation_candidates": (
            ["read_only_analysis", "mutation_execution"] if ambiguous else [request_mode]
        ),
    }


def validate_cursor(cursor: Any, now: datetime) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(cursor, dict):
        return None, ["missing_verified_goal_cursor"]
    reasons: list[str] = []
    if cursor.get("issuer") not in ENTRY_CONTRACT["trusted_cursor_issuers"]:
        reasons.append("untrusted_cursor_issuer")
    if cursor.get("verification_status") != "verified" or not cursor.get("proof_ref"):
        reasons.append("unverified_goal_cursor")
    if not cursor.get("goal_id") or not isinstance(cursor.get("revision"), int) or cursor.get("revision") < 0:
        reasons.append("invalid_goal_cursor_identity")
    if not isinstance(cursor.get("state_source"), str) or not cursor.get("state_source"):
        reasons.append("missing_cursor_state_source")
    if not cursor.get("conversation_correlation") and not cursor.get("thread_id"):
        reasons.append("missing_cursor_correlation")
    if cursor.get("status") not in {"active", "paused", "complete"}:
        reasons.append("invalid_goal_cursor_status")
    issued = parse_timestamp(cursor.get("issued_at"))
    if issued is None or issued > now:
        reasons.append("invalid_cursor_issued_at")
    expires = parse_timestamp(cursor.get("expires_at"))
    if cursor.get("expires_at") and (expires is None or expires <= now):
        reasons.append("expired_goal_cursor")
    return (dict(cursor) if not reasons else None), reasons


def select_cursor(explicit: Any, candidates: Any, correlation: str | None, now: datetime) -> tuple[Any, list[Any], list[str]]:
    if explicit is not None:
        valid, reasons = validate_cursor(explicit, now)
        return valid, [], reasons
    if candidates is None:
        return None, [], ["missing_verified_goal_cursor"]
    if not isinstance(candidates, list):
        raise ValueError("active goals must be a JSON array")
    valid_candidates = []
    for candidate in candidates:
        valid, _ = validate_cursor(candidate, now)
        if valid:
            valid_candidates.append(valid)
    valid_candidates.sort(key=lambda item: str(item.get("issued_at", "")), reverse=True)
    exact = [item for item in valid_candidates if correlation and item.get("conversation_correlation") == correlation]
    if len(exact) == 1:
        return exact[0], valid_candidates, []
    if len(valid_candidates) == 1:
        return valid_candidates[0], valid_candidates, []
    if len(valid_candidates) > 1:
        return None, valid_candidates, ["multiple_goal_candidates"]
    return None, [], ["missing_verified_goal_cursor"]


def validate_attestations(value: Any, required: list[str], session_id: str, fingerprint: str, now: datetime) -> dict[str, Any]:
    if value is None:
        attestations = []
    elif isinstance(value, list):
        attestations = value
    else:
        raise ValueError("provider attestations must be a JSON array")
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    capabilities: set[str] = set()
    for item in attestations:
        reasons: list[str] = []
        if not isinstance(item, dict):
            rejected.append({"provider_id": None, "reasons": ["invalid_attestation_shape"]})
            continue
        if not isinstance(item.get("provider_id"), str) or not item.get("provider_id"):
            reasons.append("invalid_provider_identity")
        if item.get("issuer") not in ENTRY_CONTRACT["trusted_attestation_issuers"]:
            reasons.append("untrusted_attestation_issuer")
        if item.get("verification_status") != "verified" or not item.get("proof_ref"):
            reasons.append("unverified_attestation")
        if item.get("contract_version") != ENTRY_CONTRACT["contract_version"]:
            reasons.append("incompatible_attestation_contract")
        if item.get("health") != "healthy":
            reasons.append("provider_unhealthy")
        expires = parse_timestamp(item.get("expires_at"))
        issued = parse_timestamp(item.get("issued_at"))
        if issued is None or expires is None or expires <= now or issued > now:
            reasons.append("attestation_outside_validity_window")
        scope_matches = item.get("session_id") == session_id or item.get("request_fingerprint") == fingerprint
        if not scope_matches:
            reasons.append("attestation_scope_mismatch")
        item_capabilities = item.get("capabilities")
        if not isinstance(item_capabilities, list) or not all(isinstance(capability, str) for capability in item_capabilities):
            reasons.append("invalid_attested_capabilities")
        if reasons:
            rejected.append({"provider_id": item.get("provider_id"), "reasons": reasons})
        else:
            accepted.append(str(item.get("provider_id")))
            capabilities.update(item_capabilities)
    missing = sorted(set(required) - capabilities)
    return {
        "status": "ready" if not missing and bool(required) else "not_required" if not required else "degraded",
        "accepted_providers": accepted,
        "rejected_providers": rejected,
        "attested_capabilities": sorted(capabilities),
        "missing_capabilities": missing,
        "recovery_conditions": ["supply a healthy, unexpired, trusted, session-scoped attestation"] if missing else [],
    }


def truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "y", "available"}


def active_goal(goal: Any) -> bool:
    if not isinstance(goal, dict):
        return False
    status = goal.get("status")
    if status == "active":
        return True
    payload = goal.get("goal")
    return isinstance(payload, dict) and payload.get("status") == "active"


def collect_matches(text: str, rules: list[PatternRule]) -> list[str]:
    return [rule.name for rule in rules if rule.pattern.search(text)]


def resolve_request_mode(text: str, has_active_goal: bool) -> tuple[str, list[str]]:
    matched: list[str] = []
    no_execution_matches = collect_matches(text, [PatternRule("explicit_no_execution", NO_EXECUTION_PATTERN)])
    if no_execution_matches:
        if EXPLICIT_PLANNING_PATTERN.search(text):
            return "plan_only", no_execution_matches + ["explicit_planning_with_no_execution"]
        return "report_only", no_execution_matches
    active_matches = collect_matches(text, ACTIVE_GOAL_RULES)
    if has_active_goal and active_matches:
        return "active_goal_bind", active_matches
    execution_matches = collect_matches(text, EXECUTION_RULES)
    if execution_matches:
        return "execute_goal", execution_matches

    for mode, rules in [
        ("report_only", REPORT_RULES),
        ("copy_only_handoff", HANDOFF_RULES),
        ("advisory_debate", ADVISORY_RULES),
        ("plan_only", PLAN_RULES),
    ]:
        mode_matches = collect_matches(text, rules)
        if mode_matches:
            return mode, mode_matches

    if has_active_goal:
        matched.append("active_goal_present_default_bind")
        return "active_goal_bind", matched
    return "report_only", ["default_report_only"]


def resolve_tier(text: str, request_mode: str) -> tuple[str, str, list[str]]:
    if request_mode in {"report_only", "plan_only", "copy_only_handoff"}:
        return "quick_single_agent", "intent_only", ["non_execution_intent_only"]
    if request_mode == "advisory_debate":
        return "standard_superpowers", "minimal_dispatch", ["advisory_lightweight_superpowers"]

    full_matches = collect_matches(text, FULL_TIER_RULES)
    if full_matches:
        return "full_autonomous", "full_dispatch", full_matches
    quick_matches = collect_matches(text, QUICK_TIER_RULES)
    if quick_matches:
        return "quick_single_agent", "intent_only", quick_matches
    return "standard_superpowers", "minimal_dispatch", ["default_standard_superpowers"]


def resolve_route(text: str, request_mode: str, tier: str) -> tuple[str | None, list[str]]:
    if tier == "quick_single_agent":
        return None, ["quick_has_no_superpowers_route"]
    if request_mode == "advisory_debate":
        return "writing-plans", ["advisory_uses_writing_plans"]

    for route, rules in [
        ("dispatching-parallel-agents", PARALLEL_ROUTE_RULES),
        ("systematic-debugging", DEBUG_ROUTE_RULES),
        ("test-driven-development", TEST_ROUTE_RULES),
        ("requesting-code-review", REVIEW_ROUTE_RULES),
        ("writing-plans", PLAN_ROUTE_RULES),
    ]:
        matches = collect_matches(text, rules)
        if matches:
            return route, matches
    return "subagent-driven-development", ["default_implementation_route"]


def resolve_execution_mode(
    tier: str,
    request_mode: str,
    superpowers_available: str,
    direct_runtime_requested: bool,
) -> tuple[str, list[str], dict[str, str] | None]:
    if tier == "quick_single_agent":
        return "single_agent_exception", ["quick_single_agent_exception"], None
    if direct_runtime_requested:
        return (
            "runtime_subagents",
            ["explicit_direct_runtime_requested"],
            {
                "legacy_runtime_fallback_trigger": "user_requested_direct_runtime_team",
                "legacy_runtime_fallback_reason": "user explicitly requested direct harness runtime teams",
            },
        )
    if superpowers_available == "false":
        return (
            "inline_expert_memos",
            ["superpowers_unavailable_inline_fallback"],
            {
                "subagent_runtime_blocked_category": "platform_unavailable",
                "subagent_runtime_blocked_reason": "Superpowers is unavailable",
            },
        )
    if request_mode == "advisory_debate":
        return "superpowers_subagents", ["advisory_superpowers_subagents"], None
    return "superpowers_subagents", ["standard_superpowers_subagents"], None


def normalize_readiness(readiness_status: str, request_mode: str) -> str:
    if readiness_status != "auto":
        return readiness_status
    if request_mode in {"execute_goal", "active_goal_bind"}:
        return "pending"
    return "not_required"


def resolve_goal_action(
    request_mode: str,
    readiness_status: str,
    has_active_goal: bool,
    objective_length: int | None,
) -> tuple[str, list[str]]:
    if request_mode not in {"execute_goal", "active_goal_bind"}:
        return "none", ["non_execution_no_goal_action"]
    if readiness_status != "passed":
        return "fallback_handoff", [f"readiness_{readiness_status}"]
    if objective_length is not None and objective_length > 4000:
        return "fallback_handoff", ["objective_over_4000"]
    if has_active_goal:
        return "bind_active_goal", ["active_goal_parent_bound"]
    return "create_goal", ["create_parent_goal"]


def resolve_task_profile(text: str, request_mode: str) -> tuple[str | None, list[str]]:
    if request_mode not in {"execute_goal", "active_goal_bind"}:
        return None, ["non_execution_has_no_runtime_profile"]
    research_matches = collect_matches(text, RESEARCH_PROFILE_RULES)
    if research_matches:
        return "scientific_autoresearch", research_matches
    return "complex_engineering", ["default_complex_engineering_profile"]


def validate_runtime_state(runtime_state: Any) -> dict[str, Any] | None:
    if runtime_state is None:
        return None
    if not isinstance(runtime_state, dict):
        raise ValueError("runtime state must be a JSON object")
    goal = runtime_state.get("goal")
    if not isinstance(goal, dict) or not goal.get("id"):
        raise ValueError("runtime state goal must be an object with a non-empty id")
    if goal.get("status") not in {"active", "paused", "complete"}:
        raise ValueError(f"unknown goal status: {goal.get('status')}")
    roadmap = runtime_state.get("roadmap")
    if roadmap is not None:
        if not isinstance(roadmap, dict):
            raise ValueError("runtime state roadmap must be an object")
        if not roadmap.get("goal_id"):
            raise ValueError("runtime state roadmap requires goal_id")
        allowed = {"draft", "pending_approval", "approved"}
        if roadmap.get("status") not in allowed:
            raise ValueError(f"unknown roadmap status: {roadmap.get('status')}")
    accepted_milestone = runtime_state.get("accepted_milestone")
    if accepted_milestone is not None:
        if not isinstance(accepted_milestone, dict):
            raise ValueError("runtime state accepted_milestone must be an object")
        if not accepted_milestone.get("id") or not accepted_milestone.get("goal_id"):
            raise ValueError("runtime state accepted_milestone requires id and goal_id")
        if accepted_milestone.get("status") != "accepted":
            raise ValueError("runtime state accepted_milestone must have status accepted")
    active_work = runtime_state.get("active_work")
    if active_work is not None and not isinstance(active_work, list):
        raise ValueError("runtime state active_work must be an array")
    for work in active_work or []:
        if not isinstance(work, dict) or not work.get("goal_id") or not work.get("milestone_id"):
            raise ValueError("each active_work entry requires goal_id and milestone_id")
        if work.get("status") not in {"active", "blocked", "terminal"}:
            raise ValueError(f"unknown active_work status: {work.get('status')}")
    return runtime_state


def authority_goal_ids(runtime_state: dict[str, Any] | None) -> set[str]:
    if not runtime_state:
        return set()
    ids: set[str] = set()
    goal = runtime_state.get("goal")
    if isinstance(goal, dict) and goal.get("id"):
        ids.add(str(goal["id"]))
    for key in ("roadmap", "accepted_milestone"):
        value = runtime_state.get(key)
        if isinstance(value, dict) and value.get("goal_id"):
            ids.add(str(value["goal_id"]))
    for work in runtime_state.get("active_work") or []:
        if isinstance(work, dict) and work.get("goal_id"):
            ids.add(str(work["goal_id"]))
    return ids


def resolve_lifecycle(
    request_mode: str,
    has_active_goal: bool,
    runtime_state: dict[str, Any] | None,
) -> tuple[str, str, list[str]]:
    if request_mode not in {"execute_goal", "active_goal_bind"}:
        return "not_applicable", "not_required", ["non_execution_lifecycle"]
    goal_ids = authority_goal_ids(runtime_state)
    if len(goal_ids) > 1:
        return "state_required", "state_required", ["conflicting_authority_goal_ids"]
    if runtime_state:
        goal = runtime_state.get("goal")
        if isinstance(goal, dict) and goal.get("status") == "complete":
            return "goal_complete", "closed", ["durable_goal_complete"]
        if not has_active_goal:
            return "resume_required", "handoff_required", ["durable_goal_requires_binding"]
        roadmap = runtime_state.get("roadmap")
        active_work = runtime_state.get("active_work") or []
        if active_work:
            return "resume_required", "authorized", ["durable_active_work_present"]
        if not roadmap:
            return "roadmap_required", "owner_approval_required", ["durable_roadmap_missing"]
        if roadmap["status"] in {"draft", "pending_approval"}:
            return "roadmap_pending_approval", "owner_approval_required", ["roadmap_not_approved"]
        return "milestone_ready", "authorized", ["approved_roadmap_ready"]
    if has_active_goal or request_mode == "active_goal_bind":
        return "resume_required", "authorized", ["active_goal_requires_durable_resume"]
    return "roadmap_required", "owner_approval_required", ["new_goal_requires_roadmap"]


def normalize_capabilities(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        value = value.get("capabilities", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("capabilities must be an array of capability names")
    return sorted(set(value))


def resolve_provider(
    task_profile: str | None,
    capabilities: list[str],
) -> tuple[str, list[str], list[str], list[str]]:
    unknown = sorted(set(capabilities) - KNOWN_CAPABILITIES)
    available = sorted(set(capabilities) & KNOWN_CAPABILITIES)
    if task_profile is None:
        return ("incompatible" if unknown else "standalone"), available, [], unknown
    required = list(RUNTIME_PROFILES[task_profile]["required_capabilities"])
    missing = sorted(set(required) - set(available))
    if unknown:
        status = "incompatible"
    elif missing:
        status = "degraded"
    else:
        status = "full_stack"
    return status, available, missing, unknown


def resolve_next_owner(lifecycle_state: str) -> str | None:
    if lifecycle_state == "not_applicable":
        return None
    if lifecycle_state in {"roadmap_required", "roadmap_pending_approval"}:
        return "goal-plan"
    if lifecycle_state in {"resume_required", "state_required"}:
        return "goal-context"
    if lifecycle_state == "goal_complete":
        return "goal-close"
    return "goal-preflight"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve harness goal-entry behavior")
    parser.add_argument("--request")
    parser.add_argument("--request-file")
    parser.add_argument("--objective")
    parser.add_argument("--objective-file")
    parser.add_argument("--conversation-mode", choices=["plan", "default"], default="default")
    parser.add_argument("--active-goal-json")
    parser.add_argument("--runtime-state-json")
    parser.add_argument("--capabilities-json")
    parser.add_argument("--request-parts-json")
    parser.add_argument("--clarification-json")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--prior-entry-session-json")
    parser.add_argument("--goal-cursor-json")
    parser.add_argument("--active-goals-json")
    parser.add_argument("--expected-goal-revision", type=int)
    parser.add_argument("--conversation-correlation")
    parser.add_argument("--provider-attestations-json")
    parser.add_argument("--active-phase-id")
    parser.add_argument("--readiness-status", choices=sorted(READINESS_STATUSES), default="auto")
    parser.add_argument("--superpowers-available", choices=["true", "false", "unknown"], default="unknown")
    parser.add_argument("--direct-runtime-requested", action="store_true")
    parser.add_argument("--json", action="store_true", help="accepted for compatibility; output is always JSON")
    return parser.parse_args(argv)


def resolve(args: argparse.Namespace) -> dict[str, Any]:
    request_text = read_text_arg(args.request, args.request_file)
    objective_text = read_text_arg(args.objective, args.objective_file)
    request_parts = normalize_request_parts(
        request_text,
        load_json_arg(getattr(args, "request_parts_json", None)),
    )
    clarification = load_json_arg(getattr(args, "clarification_json", None))
    authoritative_instruction = str(request_parts["instruction"])
    semantic_instruction = str((clarification or {}).get("instruction", authoritative_instruction))
    active_goal_json = load_json_arg(args.active_goal_json)
    goal_cursor_input = getattr(args, "goal_cursor_json", None)
    active_goals_input = getattr(args, "active_goals_json", None)
    has_active_goal = active_goal(active_goal_json) or bool(goal_cursor_input) or bool(active_goals_input)
    runtime_state = validate_runtime_state(load_json_arg(getattr(args, "runtime_state_json", None)))
    capabilities = normalize_capabilities(load_json_arg(getattr(args, "capabilities_json", None)))

    request_mode, request_matches = resolve_request_mode(semantic_instruction, has_active_goal)
    tier, dispatch_level, tier_matches = resolve_tier(semantic_instruction, request_mode)
    route, route_matches = resolve_route(semantic_instruction, request_mode, tier)
    execution_mode, execution_matches, fallback = resolve_execution_mode(
        tier,
        request_mode,
        args.superpowers_available,
        args.direct_runtime_requested,
    )
    readiness_status = normalize_readiness(args.readiness_status, request_mode)
    objective_length = len(objective_text) if objective_text else None
    goal_action, goal_action_matches = resolve_goal_action(
        request_mode,
        readiness_status,
        has_active_goal,
        objective_length,
    )
    task_profile, profile_matches = resolve_task_profile(semantic_instruction, request_mode)
    lifecycle_state, authorization_state, lifecycle_matches = resolve_lifecycle(
        request_mode,
        has_active_goal,
        runtime_state,
    )
    provider_status, available_capabilities, missing_capabilities, unknown_capabilities = resolve_provider(
        task_profile,
        capabilities,
    )

    semantic_pass = build_semantic_pass(authoritative_instruction, request_mode, clarification)
    fingerprint_payload = {
        "contract_version": ENTRY_CONTRACT["contract_version"],
        "request_parts": request_parts,
        "clarification": clarification,
        "conversation_mode": args.conversation_mode,
        "conversation_correlation": getattr(args, "conversation_correlation", None),
    }
    request_fingerprint = stable_digest(fingerprint_payload)
    idempotency_key = getattr(args, "idempotency_key", None) or f"auto:{request_fingerprint}"
    session_id = f"entry-{stable_digest({'key': idempotency_key, 'fingerprint': request_fingerprint})[:20]}"
    prior_session = load_json_arg(getattr(args, "prior_entry_session_json", None))
    idempotency_status = "new"
    idempotency_conflict = False
    if prior_session is not None:
        if not isinstance(prior_session, dict):
            raise ValueError("prior entry session must be a JSON object")
        prior_key = (prior_session.get("idempotency") or {}).get("key")
        if prior_key == idempotency_key and prior_session.get("request_fingerprint") == request_fingerprint:
            session_id = str(prior_session.get("session_id", session_id))
            idempotency_status = (
                "replayed_completed" if prior_session.get("status") == "complete" else "replayed_in_progress"
            )
        else:
            idempotency_status = "conflict"
            idempotency_conflict = True

    now = datetime.now(timezone.utc)
    if semantic_pass["mutation_candidate"]:
        selected_cursor, goal_candidates, cursor_reasons = select_cursor(
            load_json_arg(goal_cursor_input),
            load_json_arg(active_goals_input),
            getattr(args, "conversation_correlation", None),
            now,
        )
    else:
        selected_cursor, goal_candidates, cursor_reasons = None, [], []
    if getattr(args, "expected_goal_revision", None) is not None and selected_cursor:
        if selected_cursor["revision"] != args.expected_goal_revision:
            cursor_reasons.append("stale_goal_revision")
            selected_cursor = None

    phase_graph = semantic_pass["phase_graph"]
    explicit_active_phase_id = getattr(args, "active_phase_id", None)
    active_phase_id = explicit_active_phase_id or (phase_graph[0]["phase_id"] if phase_graph else None)
    active_phase = next((phase for phase in phase_graph if phase["phase_id"] == active_phase_id), None)
    invalid_active_phase = bool(explicit_active_phase_id and active_phase is None)
    required_attested = (
        list(RUNTIME_PROFILES[active_phase["runtime_profile"]]["required_capabilities"])
        if semantic_pass["mutation_candidate"] and active_phase
        else []
    )
    attestation = validate_attestations(
        load_json_arg(getattr(args, "provider_attestations_json", None))
        if semantic_pass["mutation_candidate"] and not invalid_active_phase
        else None,
        required_attested,
        session_id,
        request_fingerprint,
        now,
    )

    authority_reasons: list[str] = []
    goal_mutation_allowed = False
    phase_execution_allowed = False
    if semantic_pass["status"] != "resolved":
        authority_status = "blocked"
        authority_reasons.append("semantic_intent_unresolved")
    elif not semantic_pass["mutation_candidate"]:
        authority_status = "not_required"
    elif idempotency_conflict:
        authority_status = "conflict"
        authority_reasons.append("idempotency_fingerprint_conflict")
    elif invalid_active_phase:
        authority_status = "blocked"
        authority_reasons.append("invalid_active_phase")
    elif "multiple_goal_candidates" in cursor_reasons:
        authority_status = "goal_selection_required"
        authority_reasons.extend(cursor_reasons)
    else:
        cursor_required = has_active_goal or request_mode == "active_goal_bind"
        if cursor_required and selected_cursor is None:
            authority_status = "blocked"
            authority_reasons.extend(cursor_reasons)
        elif readiness_status != "passed":
            authority_status = "blocked"
            authority_reasons.append(f"readiness_{readiness_status}")
        else:
            goal_mutation_allowed = True
            if attestation["status"] == "ready":
                authority_status = "ready"
                phase_execution_allowed = True
            else:
                authority_status = "planning_only"
                authority_reasons.append("phase_provider_attestation_required")

    authority_pass = {
        "status": authority_status,
        "goal_mutation_allowed": goal_mutation_allowed,
        "phase_execution_allowed": phase_execution_allowed,
        "active_phase_id": active_phase_id,
        "cursor": selected_cursor,
        "goal_candidates": goal_candidates,
        "provider": attestation,
        "reasons": list(dict.fromkeys(authority_reasons)),
    }
    if lifecycle_state == "state_required":
        goal_action = "fallback_handoff"
        goal_action_matches = ["runtime_state_conflict"]
    elif "durable_goal_requires_binding" in lifecycle_matches:
        goal_action = "fallback_handoff"
        goal_action_matches = ["durable_goal_not_active"]
    elif task_profile is not None and provider_status in {"degraded", "incompatible"}:
        authorization_state = "handoff_required"
    if semantic_pass["status"] != "resolved" or idempotency_conflict:
        goal_action = "none"
        goal_action_matches = ["entry_session_mutation_blocked"]
        authorization_state = "handoff_required"
    elif semantic_pass["mutation_candidate"] and not authority_pass["goal_mutation_allowed"]:
        goal_action = "fallback_handoff"
        goal_action_matches = ["entry_session_authority_blocked"]
        authorization_state = "handoff_required"

    if request_mode == "advisory_debate":
        harness_mode = "advisory_harness"
    elif tier == "quick_single_agent":
        harness_mode = "single_agent_exception"
    elif request_mode in {"execute_goal", "active_goal_bind"}:
        harness_mode = "goal_scoped_autonomous_harness"
    else:
        harness_mode = None

    run_dir_required = harness_mode == "goal_scoped_autonomous_harness" and tier != "quick_single_agent"
    matched_rules = (
        request_matches
        + tier_matches
        + route_matches
        + execution_matches
        + goal_action_matches
        + profile_matches
        + lifecycle_matches
    )
    decision: dict[str, Any] = {
        "version": 1,
        "resolved_at": utc_now(),
        "conversation_mode": args.conversation_mode,
        "request_mode": request_mode,
        "goal_entry_tier": tier,
        "superpowers_dispatch_level": dispatch_level,
        "subagent_execution_mode": execution_mode,
        "harness_mode": harness_mode,
        "superpowers_route": route,
        "goal_action": goal_action,
        "readiness_gate": {
            "required": request_mode in {"execute_goal", "active_goal_bind"},
            "status": readiness_status,
        },
        "run_dir_required": run_dir_required,
        "matched_rules": matched_rules,
        "reason": "; ".join(matched_rules),
        "decision_contract": {
            "version": 2,
            "task_profile": task_profile,
            "lifecycle_state": lifecycle_state,
            "authorization_state": authorization_state,
            "provider_status": provider_status,
            "verifier_requirement": "independent" if task_profile else "not_applicable",
            "required_capabilities": list(RUNTIME_PROFILES[task_profile]["required_capabilities"])
            if task_profile
            else [],
            "available_capabilities": available_capabilities,
            "missing_capabilities": missing_capabilities,
            "unknown_capabilities": unknown_capabilities,
            "next_owner": resolve_next_owner(lifecycle_state),
        },
        "entry_session": {
            "version": ENTRY_CONTRACT["contract_version"],
            "status": "complete" if idempotency_status == "replayed_completed" else "in_progress",
            "session_id": session_id,
            "request_fingerprint": request_fingerprint,
            "idempotency": {
                "key": idempotency_key,
                "key_source": "client" if getattr(args, "idempotency_key", None) else "derived_compatibility",
                "status": idempotency_status,
            },
            "semantic_pass": semantic_pass,
            "authority_pass": authority_pass,
        },
    }
    if objective_length is not None:
        decision["create_goal_objective_length"] = objective_length
    if fallback:
        decision.update(fallback)
    return decision


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    decision = resolve(args)
    json.dump(decision, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
