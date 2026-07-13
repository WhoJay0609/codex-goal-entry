# Codex Goal Entry

`goal-entry` 是一个显式调用、模型原生的通用任务入口。本仓库同时维护它所需的
十个内部 `goal-*` skills。它保持轻量：模型负责理解任务，机械工具链只保护授权、
状态、证据、恢复和完成条件。

当前版本：`v2.0.0`。

## 三层执行

显式调用 `goal-entry` 后，模型从完整对话选择一个执行层级：

| 层级 | 使用条件 | 状态开销 |
| --- | --- | --- |
| `direct` | 回答、解释、检查、诊断等只读工作 | 不创建 Goal artifact |
| `compound` | 一个边界清晰的修改、修复、测试或文档任务 | 由 Compound Engineering 或用户点名 skill 执行 |
| `goal` | 需要跨轮次恢复、依赖阶段、里程碑、重复迭代、监控或多阶段验收 | 创建一个 durable Goal |
| `none` | 用户明确不要执行，或尚不足以安全修改 | 不修改 |

`goal` 并不替代 Compound Engineering。Goal 管生命周期、依赖、验收和收尾；
Compound Engineering 仍执行其中一个个有限范围工程单元。短回复如 `1`、`继续`
和 `可以` 继承当前任务、层级和用户点名 skill，不能脱离上下文重新猜测。

## Goal 完整闭环

新 Goal 依次经过：

```text
planning -> active -> verifying -> completed
     \          \           \
      +----------+-----------+-> blocked
```

planning 固化任务图、milestone、依赖、验收标准和稳定 Issue identity。每个
milestone 一个主 Issue；只有可独立交付、独立验收或真正阻塞的单元才产生子 Issue。
失败按 runtime profile 有限重试，耗尽后只自动 replan 一次且不能改已验收结果或
原始授权边界。

verifying 要求所有单元集成、每个 milestone 有机械证据、高风险单元和最终 PR
claim 有独立 verifier、runtime handle 已回收、Goal tool 已按序同步，并且在原请求
授权 `pr.create` 时取得已对账 PR identity。Goal 在 open PR 处完成；merge 和持续
review 默认不属于这个 Goal。

## 轻量机械边界

- `references/model_route_contract.json` 只验证模型给出的 route shape、只读/修改
  边界、no-execution、短回复继承、目标长度、外部授权和 resume cursor；不含语义
  regex 或中央 skill map。
- `goal-preflight` 绑定 model route、目标、authorization scope、幂等 identity 和
  verified cursor，但不会重新分类。
- `goal-backend` 仍只有六个 capability：初始化、证据记录、trace 校验、runtime
  cleanup、Goal sync、legacy trace 读取。
- 原子 `manifest.json` 是状态真源；`events.jsonl` 是审计/恢复 journal。
- Issue/PR 写入先记录 intent；provider 结果不确定时先 reconcile，绝不盲目重复
  create。未授权 draft 不能提交 provider outcome；artifact 不保存凭据或 raw
  provider payload。
- Goal tools、provider calls 和 backend mutation 仅由主编排器执行。九类专家只能
  使用注册 skill family；`goal-*`、Goal tools、LFG、ce-work、规划/发布类递归
  orchestrator 全局拒绝。前端/UI expert 已内置。

## Model route 与 preflight

模型输出 `goal-entry.model-route.v1` 后，Goal 路径可这样进行机械验证：

```bash
python3 scripts/validate_model_route.py --route-json /path/to/model-route.json
python3 skills/goal-preflight/scripts/run_goal_preflight.py \
  --model-route-json /path/to/model-route.json \
  --readiness-status passed
```

正常路径不运行 legacy resolver。需要检查旧路由行为时，可显式运行诊断 CLI：

```bash
python3 scripts/resolve_goal_entry.py \
  --request 'PLEASE IMPLEMENT THIS PLAN with tests' \
  --readiness-status passed
```

## 目录

- `SKILL.md`：public thin router。
- `references/model_route_contract.json`：模型 route envelope。
- `skills/goal-preflight/`：route/session/context readiness 绑定。
- `skills/goal-backend/`：六能力 kernel、生命周期、Issue/PR、恢复和验收门槛。
- `skills/goal-plan|dispatch|team|trace|close/`：各自单一职责协议。
- `scripts/resolve_goal_entry.py`：legacy diagnostics/offline compatibility。
- `scripts/install_goal_stack.py`：事务式临时/本地安装与回滚。

## 验证

```bash
python3 scripts/quick_validate.py .
python3 scripts/resolve_goal_entry.py \
  --request 'PLEASE IMPLEMENT THIS PLAN with tests' \
  --readiness-status passed
python3 scripts/check_goal_stack.py .
python3 -m unittest discover -s tests -p 'test_*.py'
```
