---
name: statem-deepseek
description: DeepSeek reference profile for the host-neutral StateM harness bridge. Use with DeepSeek V4-Flash or V4-Pro while keeping the shared runbook and transition gates model-independent.
---

# StateM DeepSeek Reference Profile

This skill is a DeepSeek-specific example layered on top of the generic
`statem-harness` contract. Do not treat DeepSeek or OpenCode as architectural
requirements of StateM.

## Start or resume

1. Use a shared StateM runbook; `examples/deepseek-coding-agent.yaml` is a useful
   reference but not a required host format.
2. Validate with `statem validate <spec> --json`.
3. Start/resume with `statem start <spec> --run-id <id> --json`.
4. Before acting, run `statem cur --json`.
5. Follow the current node prompt and move only with `statem goto <next-state> --json`.
6. Read `statem history --tail 10 --json` after compaction or when resuming.

## Host-neutral bridge

A DeepSeek-oriented harness should consume:

```bash
python3 -m statem.harness_bridge context  --model deepseek-v4-flash
python3 -m statem.harness_bridge decision --model deepseek-v4-flash
python3 -m statem.harness_bridge compact  --model deepseek-v4-flash
```

Replace the model id with `deepseek-v4-pro` for Pro. The bridge auto-selects the
appropriate profile while preserving the same StateM graph and gates.

## DeepSeek execution policy

Apply DeepSeek-specific adaptation mainly in verification and self-review rather
than rewriting the whole workflow.

- Prefer fresh, consumer-facing checks over logs, intuition, or repeated reflection.
- When the concrete task reveals a regression condition, register a StateM dynamic
  check so the requirement becomes executable and durable.
- In self-review, use at most one bounded countercheck unless it reveals a concrete
  failure that creates new evidence.
- Do not alter a passing candidate without concrete contradictory evidence.
- A concrete failure routes to repair; repair must return to verification.
- Never declare completion before a terminal handoff state.

### V4-Flash

Keep each pass narrow and tool-driven. Avoid re-deriving the entire plan after a
small failure. Once deterministic verification passes, spend the review budget on
one targeted countercheck rather than broad speculative exploration.

### V4-Pro

Use the extra reasoning capacity for architecture, ambiguous failures, and review,
but keep the same bounded evidence contract. Deeper reasoning is useful only when
it changes a concrete plan, check, or repair decision.

Override automatic profile detection with
`STATEM_HARNESS_PROFILE=deepseek-flash` or
`STATEM_HARNESS_PROFILE=deepseek-pro`. Legacy
`STATEM_DEEPSEEK_PROFILE=flash|pro` remains accepted for compatibility.
