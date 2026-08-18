# StateM Harness Bridge

This directory documents the host-neutral integration seam between StateM and any
agent harness.

The core contract lives in `statem.harness_bridge`. A host does not need to know
StateM's internal file layout and StateM does not need to know the host's plugin
API. The host only needs three lifecycle points:

1. **before model turn** — append the bridge `system_context`;
2. **idle / stop** — inspect the bridge continuation decision and optionally send
   the returned prompt back into the same agent session;
3. **context compaction** — preserve the returned `compaction_context`.

DeepSeek V4-Flash/Pro are included as model profiles and examples, not as a hard
architectural dependency.

## JSON contract

From the working repository with an active StateM run:

```bash
python3 -m statem.harness_bridge snapshot \
  --model deepseek-v4-flash \
  --state-dir .statem
```

The bridge returns a stable JSON envelope like:

```json
{
  "schema_version": 1,
  "managed": true,
  "profile": "deepseek-flash",
  "model": "deepseek-v4-flash",
  "run_id": "my-task",
  "current": "verify",
  "entry_id": "...",
  "next": ["repair", "self_review"],
  "terminal": false,
  "system_context": "...",
  "continuation": {
    "decision": "continue",
    "prompt": "..."
  },
  "compaction_context": "...",
  "limits": {
    "max_continuations": 12,
    "max_stagnant_turns": 3
  }
}
```

Narrow views are available for hosts that only need one lifecycle surface:

```bash
python3 -m statem.harness_bridge context  --model deepseek-v4-pro
python3 -m statem.harness_bridge decision --model deepseek-v4-pro
python3 -m statem.harness_bridge compact  --model deepseek-v4-pro
```

If no active StateM run exists, the bridge returns `"managed": false` and the
host should behave exactly as it normally would.

## Host adapter contract

A minimal host plugin should behave approximately like this:

```text
before_turn(model):
    bridge = context(model)
    if bridge.managed:
        append bridge.system_context to the existing system context

on_idle_or_stop(model):
    bridge = decision(model)
    if not bridge.managed or bridge.continuation.decision == "stop":
        allow stop
    else:
        send bridge.continuation.prompt to the same session

on_compaction(model):
    bridge = compact(model)
    if bridge.managed:
        preserve bridge.compaction_context
```

The host should track `entry_id`. If it stays unchanged for
`max_stagnant_turns` consecutive continuation turns, pause auto-looping rather
than burning tokens indefinitely. Also enforce `max_continuations` per idle/stop
cycle.

The bridge never calls `statem goto`. State transitions remain explicit model or
user actions and still pass StateM's executable gates.

## Profiles

Profiles change model-facing execution guidance, not StateM semantics.

- `generic`: works with any model/harness;
- `deepseek-flash`: narrow, tool-driven passes and early deterministic checks;
- `deepseek-pro`: deeper architecture/review reasoning while keeping bounded
  verification;
- `auto`: detects DeepSeek V4-Flash/Pro from the model id, otherwise falls back
  to `generic`.

Override auto-detection with:

```bash
export STATEM_HARNESS_PROFILE=generic
export STATEM_HARNESS_PROFILE=deepseek-flash
export STATEM_HARNESS_PROFILE=deepseek-pro
```

Legacy `STATEM_DEEPSEEK_PROFILE=flash|pro` is still accepted.

Cost/loop brakes are host-neutral:

```bash
export STATEM_HARNESS_MAX_CONTINUATIONS=8
export STATEM_HARNESS_MAX_STAGNANT_TURNS=2
```

## DeepSeek Harness example

`examples/deepseek_harness_example.py` shows the smallest Python-style adapter
for a DeepSeek-oriented harness. It deliberately uses generic callback names
(`before_turn`, `on_idle`, `on_compaction`) because DeepSeek's public API defines
the model transport, not one mandatory harness plugin ABI.

The important separation is:

```text
DeepSeek model / provider
        ↓
DeepSeek Harness (or any other host)
        ↓
small host adapter
        ↓
python -m statem.harness_bridge
        ↓
StateM runbook + gates
```

The existing OpenCode integration is another host adapter and can consume the
same bridge. New hosts should implement this contract rather than copy
DeepSeek-specific policy into their plugin code.
