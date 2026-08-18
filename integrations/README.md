# StateM integrations

StateM integrations are organized around a host-neutral bridge rather than a
model-specific harness.

## Architecture

```text
                    StateM runbook/runtime
                            │
                            ▼
                  statem-harness JSON bridge
                    (statem.harness_bridge)
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
   DeepSeek Harness     OpenCode adapter   other host adapter
      example             example           future/custom
          │                 │                 │
          ▼                 ▼                 ▼
   DeepSeek V4-*       any host model      any model/provider
```

The bridge owns the common execution contract:

- current StateM state and legal transitions;
- model-facing state context;
- stop/continue decision and continuation prompt;
- compaction recovery context;
- continuation and stagnation limits;
- thin model profiles such as DeepSeek V4-Flash/Pro.

Host adapters should only translate lifecycle events into bridge calls. They
should not duplicate StateM transition semantics or model profile policy.

## Entry points

- `harness/README.md` — canonical host-neutral adapter contract;
- `harness/examples/deepseek_harness_example.py` — DeepSeek Harness-style
  reference adapter;
- `opencode/statem_harness.js` — runnable OpenCode adapter using the same bridge;
- `opencode/statem_deepseek.js` — backward-compatible wrapper for older installs;
- `claude/` — existing Claude Code integration;
- `harbor/` — benchmark/Harbor integrations.

## Recommended new-host workflow

1. Install StateM so `statem` and `statem-harness` are on PATH.
2. Start a normal StateM run in the target project.
3. Before each model turn, call `statem-harness context --model <id>` and append
   `system_context` if `managed=true`.
4. When the host wants to stop, call `statem-harness decision --model <id>`.
5. Continue only when the bridge returns `decision=continue`, and respect the
   returned loop limits.
6. During context compaction, preserve `statem-harness compact --model <id>`.
7. Keep `statem goto` explicit; the adapter must never advance StateM on its own.

DeepSeek is a useful first profile because V4-Flash and V4-Pro have different
cost/reasoning tradeoffs, but the bridge defaults to a generic profile for every
other model.
