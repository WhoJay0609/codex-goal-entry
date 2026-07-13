# Codex Goal Entry and Goal Skills

`goal-entry` 是一个小型分流器；本仓库同时维护它所调用的内部 `goal-*` 家族
skills。它不是日常工程执行框架。

- 日常工程任务默认进入 **Compound Engineering**：实现、修复、测试、review、文档、有限范围的计划。
- 只有用户明确创建/恢复一个长期、持续、自治或科研循环的 **Goal** 时，才进入 Goal lifecycle。

当前维护版本：`v1.0.0`。

## Goal family

`skills/` 保存 Goal lifecycle 的内部协议，当前包括：

`goal-preflight`、`goal-context`、`goal-objective`、`goal-plan`、
`goal-dispatch`、`goal-team`、`goal-backend`、`goal-trace`、
`goal-metadata` 和 `goal-close`。

`goal-backend` 只提供六类机械能力：run 初始化、证据记录、trace 校验、运行时
清理、Goal 同步和旧 trace 的只读读取。规划、provider 选择、专家选择和 dispatch
仍由各自的 Goal skill 与主编排器负责。专家注册表固定为九类，并包含前端与 UI
工程专家；skill family 授权默认拒绝，硬拒绝规则优先。

## 为什么这样拆分

原先把普通执行请求也包装成 Goal，会让每次工程任务都携带 readiness、runtime profile、cursor、provider attestation 和生命周期输出。它既重，也和 Compound Engineering 的工程流程重复。

现在 resolver 先做一个小决策：

| 请求 | `execution_destination` | 后续 |
| --- | --- | --- |
| “请修复解析器并补测试” | `compound_engineering` | 交给 Compound Engineering |
| “请创建一个长期 Goal，持续运行科研实验循环” | `goal_lifecycle` | 进入 Goal preflight 与生命周期 |
| “继续这个 Goal” | `goal_lifecycle` | 用 verified cursor 恢复 |
| “只分析，不要执行” | `null` | 不执行 |

普通路径不会解析 active Goal、cursor、runtime state、capability 或 attestation
输入，也不会输出 `decision_contract` 或 `entry_session`。

## 使用

```bash
# 日常工程：默认 Compound Engineering
python3 scripts/resolve_goal_entry.py \
  --request '请修复解析器并添加回归测试'

# 显式长期 Goal：进入 Goal lifecycle
python3 scripts/resolve_goal_entry.py \
  --request '请创建一个长期 Goal，持续运行科研实验循环并整理证据' \
  --readiness-status passed
```

普通工程结果示例：

```json
{
  "request_mode": "execute_compound",
  "execution_destination": "compound_engineering",
  "goal_action": "none"
}
```

显式 Goal 结果才会附带 `decision_contract`、`entry_session`、Semantic Pass 和
Authority Pass。缺少 verified evidence 时，Goal 路径会保守停在规划或交接状态，
不会声称外部 Goal mutation 已发生。

## Goal 选择规则

触发 Goal 的最小条件是：

1. 明确创建/启动 Goal，且明确它是长期、持续、自治、multi-day 或科研循环；或
2. 明确恢复一个已有 Goal。

仅有“实现”“运行实验”“active goal”或“派子代理”都不够。`不要执行` 始终优先。

进入 Goal 后，由本仓库内的 `goal-*` family 分别负责
`goal-preflight`、`goal-objective`、`goal-context`、`goal-plan`、
`goal-dispatch`、`goal-backend`、`goal-trace`、`goal-metadata` 和
`goal-close`；`goal-entry` 自身仍只负责路由合同与只读验证，不直接创建、更新或
关闭 Goal。

## 内容与验证

- `SKILL.md`：最小公开路由合同。
- `scripts/resolve_goal_entry.py`：机器可读分流器。
- `references/entry_session_contract.json`：仅 Goal 路径使用的 intent 与证据合同。
- `references/runtime_profiles.json`：Goal runtime profiles 的可移植声明。
- `scripts/validate_goal_runtime.py`：只读 trace 验证器。
- `goal-stack-manifest.json`：声明 public `goal-entry` 与内部 Goal family 的边界。
- `scripts/check_goal_stack.py`：检查 public router 与内部 family 的一致性。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_goal_runtime.py \
  tests/fixtures/engineering_runtime_trace.json \
  tests/fixtures/autoresearch_runtime_trace.json
python3 scripts/quick_validate.py .
python3 scripts/check_goal_stack.py .
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 发布

`VERSION` 是发布版本的单一来源。更新公开合同后同时更新
`VERSION`、`CHANGELOG.md` 和相应测试，再运行 `scripts/quick_validate.py .`。
