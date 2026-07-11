# Codex Goal Entry

`goal-entry` 是一个面向 Codex goal-bound 工作流的轻量路由 skill。它本身不负责完成任务，而是先把用户请求分类，再决定后续应该走普通汇报、计划、目标创建、绑定已有 Goal、subagent 调度、backend artifact 初始化或 closeout。

**当前维护版本：`v0.1.0`**

这个仓库是从本机 Codex skill 中拆出来的公开版本，重点保留：

- `SKILL.md`: public entry contract。
- `scripts/resolve_goal_entry.py`: 请求分类器，输出机器可读 JSON。
- `references/runtime_profiles.json`: Shared Goal Kernel 与双 Runtime Profile
  的可移植声明式合同。
- `scripts/validate_goal_runtime.py`: 只读事件 trace 一致性验证器，不是执行器。
- `references/architecture.md`: `goal-entry` 与 `goal-*` 子协议的职责拆分。
- `agents/openai.yaml`: agent metadata 示例。

## 版本维护

- `VERSION` 是仓库发布版本的单一来源，当前值为 `0.1.0`。
- `CHANGELOG.md` 记录每个公开版本的用户可见能力、兼容性和修复。
- Git tag 使用 `vMAJOR.MINOR.PATCH`，例如 `v0.1.0`。
- package release version 与 resolver/contract schema version 分开演进：发布补丁不要求修改 JSON schema version；只有公开数据合同发生对应变化时才提升 schema version。
- 后续发布先更新 `VERSION` 和 `CHANGELOG.md`，通过 `scripts/quick_validate.py`，合并到默认分支后再在该合并提交上创建 tag。

## 适用场景

使用 `goal-entry` 的典型情况：

- 任务可能很长，需要 Goal objective 和 closeout。
- 用户要求继续已有目标，或需要判断是否绑定 active goal。
- 任务需要先做 readiness / preflight，再执行。
- 任务可能需要 subagent 或专家团队，但不能直接让 subagent 管理 Goal 生命周期。
- 需要把复杂请求分类成 `report_only`、`plan_only`、`execute_goal`、`active_goal_bind` 等模式。

不适合使用 `goal-entry` 的情况：

- 简单问答。
- 单文件小改动且验证很直接。
- 只需要普通代码 review。
- 用户明确说“不要执行，只讨论”。

## 快速验证

```bash
python3 scripts/quick_validate.py .
python3 scripts/resolve_goal_entry.py --request 'PLEASE IMPLEMENT THIS PLAN with tests' --readiness-status passed
```

典型输出会包含：

```json
{
  "request_mode": "execute_goal",
  "goal_entry_tier": "standard_superpowers",
  "goal_action": "create_goal",
  "decision_contract": {
    "version": 2,
    "task_profile": "complex_engineering",
    "lifecycle_state": "roadmap_required",
    "authorization_state": "handoff_required",
    "provider_status": "degraded",
    "next_owner": "goal-plan"
  },
  "readiness_gate": {
    "required": true,
    "status": "passed"
  }
}
```

顶层字段保持 version 1 兼容语义；新增的 `decision_contract` version 2
用于表达 Runtime Profile、生命周期、授权、provider 差异和下一责任 owner。
standalone 环境缺少 child provider 时会明确降级，不会把“能分类”表述成
“已经完整自治执行”。

## Runtime Profiles 与里程碑门禁

- `complex_engineering`: context → architecture boundaries → implementation →
  integration → validation → delivery → closeout。
- `scientific_autoresearch`: research bootstrap → protocol lock → experiment
  inner loop → synthesis outer loop → direction decision → evidence review →
  writing handoff。

两个 profile 共用同一组不可绕过的规则：roadmap 先审批、milestone 后执行；
implementer 不能自验收；dependent milestone 只有在独立 verdict 为 `passed`
且 subagent cleanup 完成后才能解锁；发现 drift 时先暂停受影响 branch；科研
claim 必须通过 Claim Firewall。

这个仓库负责输出和验证这些合同。真正的 milestone 调度、subagent 回收、
Goal 更新和 closeout 仍由完整环境中的外部 `goal-*` child skills 执行。

## 使用例子

### 例子 1：只做计划

```bash
python3 scripts/resolve_goal_entry.py \
  --request '请先给出迁移计划，不要执行' \
  --readiness-status not_required
```

预期方向：

- `request_mode`: `plan_only`
- `goal_action`: `none`
- 不应该创建 Goal。

### 例子 2：执行一个明确目标

```bash
python3 scripts/resolve_goal_entry.py \
  --request 'PLEASE IMPLEMENT THIS PLAN with tests' \
  --readiness-status passed \
  --objective 'Implement the confirmed plan and verify it with focused tests.'
```

预期方向：

- `request_mode`: `execute_goal`
- `readiness_gate.required`: `true`
- `goal_action`: `create_goal`

### 例子 3：中文执行请求

```bash
python3 scripts/resolve_goal_entry.py \
  --request '请帮我修改仓库里的网页指南，重新构建并推送' \
  --readiness-status passed
```

预期方向：

- 识别中文执行意图。
- 根据风险选择 quick / standard tier。
- 如果 readiness 已通过，可以进入 goal creation 或执行路由。

### 例子 4：objective 太长

```bash
python3 scripts/resolve_goal_entry.py \
  --request 'PLEASE IMPLEMENT THIS PLAN' \
  --readiness-status passed \
  --objective "$(python3 -c 'print(\"x\" * 4001)')"
```

预期方向：

- `goal_action`: `fallback_handoff`
- 原因包含 `objective_over_4000`。

## 和完整 Goal 系统的关系

这个仓库只发布 `goal-entry` 入口和 resolver。完整本机系统通常还会包含这些子 skills：

- `goal-preflight`: 执行前 readiness gate。
- `goal-objective`: 压缩 `create_goal(objective=...)` 合同。
- `goal-context`: 解析 `AGENTS.md` 层级和任务文档。
- `goal-dispatch` / `goal-team`: subagent 团队调度边界。
- `goal-trace` / `goal-close`: 验证和收尾。

公开仓库中的 `quick_validate.py` 只验证本仓库自身，不假设这些子 skills 已安装。

可以通过 `--capabilities-json` 声明当前可用 child capabilities。resolver 会
分别返回 available、missing 和 unknown capabilities，并用 `full_stack`、
`degraded`、`standalone` 或 `incompatible` 表达 provider 状态。通过
`--runtime-state-json` 提供 durable Goal/roadmap/milestone state；权威记录冲突
时返回 `state_required`，不会从对话文本猜测一个新的起点。

## 双场景一致性验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_goal_runtime.py \
  tests/fixtures/engineering_runtime_trace.json \
  tests/fixtures/autoresearch_runtime_trace.json
python3 scripts/quick_validate.py .
```

trace replay 验证 roadmap、milestone、独立验收、drift、cleanup 和 claim
规则是否一致，但不证明外部 provider 真的完成了 Goal mutation。full-stack
provider 仍需提供自己的集成证据。

## 安全边界

- 不要让 subagent 创建、更新或关闭 Goal。
- 不要跳过 readiness gate 直接创建 Goal。
- 不要把超过 4,000 字符的 objective 传给 goal creation。
- 不要把 `goal-*` 协议职责交给普通 runtime subagent。
- 不要把 capability 声明或通过的 trace replay 当作真实外部执行证据。

## 许可证

MIT。
