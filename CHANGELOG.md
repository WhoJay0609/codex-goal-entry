# Changelog

本项目从 `v0.1.0` 开始维护语义化版本。版本号遵循 `MAJOR.MINOR.PATCH`：不兼容的公开契约变化提升 MAJOR，向后兼容的新能力提升 MINOR，向后兼容的修复提升 PATCH。

## [2.0.0] - 2026-07-13

### Changed

- `goal-entry` 仍需显式调用，但调用后由模型从完整上下文选择
  `direct`、`compound`、`goal` 或 `none`，不再把 regex resolver 作为正常
  语义权威。
- `direct` 只读，有限范围修改交给 Compound Engineering；有跨轮次恢复、依赖
  阶段、里程碑、反复迭代或多阶段验收需求时，模型可自动升级为 Goal。
- Goal 新增 `planning -> active -> verifying -> completed|blocked` 生命周期、稳定
  任务图、Issue/PR 投影、有限重试与一次 replan、独立验收和 PR 完成门槛。
- backend 仍只有六个 capability；专家仍受九类注册表、skill family allowlist 和
  全局 hard deny 约束，前端/UI 专家保留。

### Safety

- Issue/PR 外部写入绑定原始授权，使用 intent、稳定 operation id、desired-state
  digest、provider reconciliation 和 outcome；未授权 draft 不能伪装成 applied，
  不确定结果不会盲目重复 create。
- 短回复复用原任务指纹；生命周期、外部 operation 与恢复 operation 可在 manifest
  写入后审计 append 中断时幂等补齐事件，不重复状态变更。
- Goal artifact 不保存 provider 凭据或原始 payload，只接受经过 schema 校验并与
  operation digest 绑定的 provider identity。
- 原子 manifest 仍是权威状态，append-only events 只承担审计与恢复，不引入第二
  planner 或通用 event-sourcing 系统。

### Compatibility

- `scripts/resolve_goal_entry.py` 和 legacy trace 继续用于诊断、离线回归和旧输入
  读取；正常 public route 与 model-route preflight 不调用它们。
- 临时安装与事务回滚仍覆盖同仓库中的 public `goal-entry` 与十个内部 `goal-*`
  skills；不会修改 live 本机 skill root。

## [1.0.0] - 2026-07-12

### Changed

- 普通工程执行现在默认输出 `execute_compound` 与
  `execution_destination=compound_engineering`，由 Compound Engineering 接管。
- 只有明确创建长期/持续/自治 Goal，或明确恢复已有 Goal，才会进入 Goal lifecycle。
- 普通路径不再解析 Goal-only 状态，也不再输出 `decision_contract` 或
  `entry_session`；这两类 envelope 只属于 explicit Goal 路径。
- `entry_session_contract` 升级到 version 2，加入可版本化的 Goal intent policy
  与小结果合同；resolver 顶层 version 升至 2，Goal `decision_contract` 升至 3。

### Removed

- 移除 Superpowers tier、dispatch level、subagent execution mode 及其 CLI 参数。
- 移除“实现/研究/active Goal 自动进入 Goal”这一隐式路由行为。

### Migration

- 需要长期 Goal 时，显式说明 “创建一个长期 Goal” 或 “继续这个 Goal”。
- 原先依赖 `goal_entry_tier`、`superpowers_dispatch_level`、
  `subagent_execution_mode` 的调用方应改读 `execution_destination`。
- public `goal-entry` 与十个内部 `goal-*` family skill 现在在同一仓库维护；旧的
  `harness-agent` 执行入口不再属于发布面。

## [0.2.0] - 2026-07-11

### Added

- additive `entry_session` version 1，将 Intent Envelope、显式复合阶段编译、Durable Goal Cursor 与阶段级 Capability Attestation 纳入同一个 Two-Pass 合同。
- 稳定请求指纹与幂等重放冲突检测；同 key 同 fingerprint 复用会话，不同 fingerprint 失败关闭。
- canonical cursor 候选选择、revision 防陈旧检查，以及只由 `goal-context` verified evidence 授权的绑定边界。
- provider attestation 的 issuer、scope、health、validity 和 capability coverage 验证，以及失效、检查点、兼容重协商的 trace conformance。

### Compatibility

- resolver 顶层 version 1 与 `decision_contract` version 2 保留为兼容投影。
- legacy capability `full_stack` 仅表达声明覆盖；只有 `entry_session.authority_pass.phase_execution_allowed` 表达当前阶段具备可执行前提。
- standalone 结果继续只证明合同一致性，不声称外部 Goal mutation 已发生。

## [0.1.0] - 2026-07-11

首个正式维护版本。

### Added

- 独立发布的 `goal-entry` router、机器可读 resolver 和 package validator。
- Shared Goal Kernel 声明式合同，以及 Complex Engineering、Scientific Autoresearch 两个 Runtime Profiles。
- additive `decision_contract` version 2，用于表达 profile、lifecycle、authorization、provider capability 和 next owner。
- durable Goal state 冲突检测、provider 降级与不兼容报告。
- 工程与科研 trace replay，覆盖 milestone gate、独立 verifier、subagent cleanup、drift correction 和 Claim Firewall。
- 中文/英文 routing、capability、失败恢复和 closeout 回归测试。

### Compatibility

- resolver 顶层 version 1 字段保持兼容。
- standalone package 只声明和验证合同；外部 `goal-*` child owners 继续负责真实 Goal mutation 与调度。

[0.1.0]: https://github.com/WhoJay0609/codex-goal-entry/releases/tag/v0.1.0
[0.2.0]: https://github.com/WhoJay0609/codex-goal-entry/releases/tag/v0.2.0
[1.0.0]: https://github.com/WhoJay0609/codex-goal-entry/releases/tag/v1.0.0
[2.0.0]: https://github.com/WhoJay0609/codex-goal-entry/releases/tag/v2.0.0
