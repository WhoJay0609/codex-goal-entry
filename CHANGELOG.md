# Changelog

本项目从 `v0.1.0` 开始维护语义化版本。版本号遵循 `MAJOR.MINOR.PATCH`：不兼容的公开契约变化提升 MAJOR，向后兼容的新能力提升 MINOR，向后兼容的修复提升 PATCH。

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
