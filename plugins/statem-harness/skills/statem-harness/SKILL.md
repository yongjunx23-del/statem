---
name: statem-harness
description: Use StateM as a host-neutral execution harness for long coding or research tasks. Works with any model/agent host that can append system context and continue an unfinished session; DeepSeek V4-Flash/Pro are reference profiles.
---

# StateM Harness

Use StateM as the authoritative procedural state for long-running work. The host
or model may change; the runbook and transition gates should remain stable.

## Core workflow

1. Find or create a StateM runbook.
2. Validate it: `statem validate <spec> --json`.
3. Start or resume it: `statem start <spec> --run-id <id> --json`.
4. Before acting, inspect `statem cur --json`.
5. Follow the current node prompt.
6. Move only through allowed edges with `statem goto <next-state> --json`.
7. Treat failed gates as concrete repair evidence, not as permission to weaken the acceptance rule.
8. Use `statem history --tail 10 --json` after context compaction or when resuming work.

## Harness bridge

Hosts should consume the stable bridge instead of reading `.statem` internals:

```bash
python3 -m statem.harness_bridge context  --model <model-id>
python3 -m statem.harness_bridge decision --model <model-id>
python3 -m statem.harness_bridge compact  --model <model-id>
```

- append `system_context` before a model turn;
- when an agent wants to stop, continue only if the bridge returns `decision=continue`;
- preserve `compaction_context` across context refresh;
- track `entry_id` and pause auto-looping if the state does not advance within the returned stagnation limit.

The bridge never advances StateM itself.

## Model profiles

The default profile is `auto`: DeepSeek V4-Flash/Pro receive their dedicated
bounded-review guidance, while other models receive the generic evidence-driven
profile. Override with `STATEM_HARNESS_PROFILE` when necessary.

Model-specific policy should remain a thin profile. Do not fork the state graph
for every model unless a verified behavioral difference requires a different
workflow contract.
