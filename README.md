# Codex Goal Entry

`goal-entry` 是一个面向 Codex goal-bound 工作流的轻量路由 skill。它本身不负责完成任务，而是先把用户请求分类，再决定后续应该走普通汇报、计划、目标创建、绑定已有 Goal、subagent 调度、backend artifact 初始化或 closeout。

这个仓库是从本机 Codex skill 中拆出来的公开版本，重点保留：

- `SKILL.md`: public entry contract。
- `scripts/resolve_goal_entry.py`: 请求分类器，输出机器可读 JSON。
- `references/architecture.md`: `goal-entry` 与 `goal-*` 子协议的职责拆分。
- `agents/openai.yaml`: agent metadata 示例。

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
  "readiness_gate": {
    "required": true,
    "status": "passed"
  }
}
```

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

## 安全边界

- 不要让 subagent 创建、更新或关闭 Goal。
- 不要跳过 readiness gate 直接创建 Goal。
- 不要把超过 4,000 字符的 objective 传给 goal creation。
- 不要把 `goal-*` 协议职责交给普通 runtime subagent。

## 许可证

MIT。
