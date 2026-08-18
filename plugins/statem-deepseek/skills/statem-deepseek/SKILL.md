---
name: statem-deepseek
description: Use StateM to manage long coding tasks with DeepSeek V4-Flash or V4-Pro, especially in OpenCode. Enforce explicit plan, execution, verification, bounded self-review, repair, and handoff states.
---

# StateM DeepSeek

Use this skill when DeepSeek V4-Flash or V4-Pro is doing a multi-step coding task
that should not rely on chat history alone.

## Start or resume

1. Prefer `examples/deepseek-coding-agent.yaml` as the default runbook.
2. Validate it with `statem validate <spec> --json`.
3. Start/resume with `statem start <spec> --run-id <id> --json`.
4. Before acting, run `statem cur --json`.
5. Follow the current node prompt and move only with `statem goto <next-state> --json`.
6. Read `statem history --tail 10 --json` when context is noisy or after compaction.

## DeepSeek execution policy

Keep the generic runbook authoritative. Apply model-specific adaptation mainly in
verification and self-review rather than rewriting the whole workflow.

- Prefer fresh, consumer-facing checks over logs, intuition, or repeated reflection.
- When the concrete task reveals a regression condition, register a StateM dynamic
  check so the requirement is executable and durable.
- In `self_review`, run at most one bounded countercheck unless it reveals a real
  failure that creates new evidence.
- Do not alter a passing candidate without concrete contradictory evidence.
- A concrete failure routes to `repair`; repair must return to `verify`.
- Never declare completion before a terminal handoff state.

### V4-Flash

Keep each pass narrow and tool-driven. Avoid re-deriving the entire plan after
small failures. Once deterministic verification passes, spend the review budget on
one targeted countercheck rather than broad speculative exploration.

### V4-Pro

Use the extra reasoning capacity for architecture, ambiguous failures, and review,
but keep the same bounded evidence contract. Deeper reasoning is useful only when
it changes a concrete plan, check, or repair decision.

The OpenCode plugin auto-detects Flash/Pro from the selected model. Override with
`STATEM_DEEPSEEK_PROFILE=flash` or `STATEM_DEEPSEEK_PROFILE=pro` if required.
