#!/usr/bin/env python3
"""Resolve harness-agent-for-goal request mode, tier, and dispatch route."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import sys
from pathlib import Path
from typing import Any


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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text_arg(value: str | None, file_value: str | None) -> str:
    if value and file_value:
        raise SystemExit("pass either inline text or a file path, not both")
    if file_value:
        return Path(file_value).read_text(encoding="utf-8")
    return value or ""


def load_json_arg(value: str | None) -> Any:
    if not value:
        return None
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


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
    if not no_execution_matches:
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

    active_matches = collect_matches(text, ACTIVE_GOAL_RULES)
    if has_active_goal and active_matches:
        return "active_goal_bind", active_matches

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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve harness goal-entry behavior")
    parser.add_argument("--request")
    parser.add_argument("--request-file")
    parser.add_argument("--objective")
    parser.add_argument("--objective-file")
    parser.add_argument("--conversation-mode", choices=["plan", "default"], default="default")
    parser.add_argument("--active-goal-json")
    parser.add_argument("--readiness-status", choices=sorted(READINESS_STATUSES), default="auto")
    parser.add_argument("--superpowers-available", choices=["true", "false", "unknown"], default="unknown")
    parser.add_argument("--direct-runtime-requested", action="store_true")
    parser.add_argument("--json", action="store_true", help="accepted for compatibility; output is always JSON")
    return parser.parse_args(argv)


def resolve(args: argparse.Namespace) -> dict[str, Any]:
    request_text = read_text_arg(args.request, args.request_file)
    objective_text = read_text_arg(args.objective, args.objective_file)
    active_goal_json = load_json_arg(args.active_goal_json)
    has_active_goal = active_goal(active_goal_json)

    request_mode, request_matches = resolve_request_mode(request_text, has_active_goal)
    tier, dispatch_level, tier_matches = resolve_tier(request_text, request_mode)
    route, route_matches = resolve_route(request_text, request_mode, tier)
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

    if request_mode == "advisory_debate":
        harness_mode = "advisory_harness"
    elif tier == "quick_single_agent":
        harness_mode = "single_agent_exception"
    elif request_mode in {"execute_goal", "active_goal_bind"}:
        harness_mode = "goal_scoped_autonomous_harness"
    else:
        harness_mode = None

    run_dir_required = harness_mode == "goal_scoped_autonomous_harness" and tier != "quick_single_agent"
    matched_rules = request_matches + tier_matches + route_matches + execution_matches + goal_action_matches
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
