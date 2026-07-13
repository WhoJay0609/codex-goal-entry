# Goal Plan Builder

Build the smallest plan that can reach the durable outcome. Each work unit must
name one owner, dependencies, risk (`low`, `medium`, or `high`), expected output,
verification, integration point, conflict owner, fallback, and wait/continue
rule. Dependencies must form an acyclic graph. Separate completed evidence from
readiness-only or proposed work.

Give every milestone and work unit a stable identity. Replanning may change only
unfinished work inside the locked authorization scope, preserves accepted
milestones, updates existing Issue mappings, and occurs automatically at most
once after retry exhaustion.
