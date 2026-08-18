# StateM + DeepSeek V4 for OpenCode

This integration turns StateM into a lightweight execution harness around
DeepSeek V4-Pro or V4-Flash when they are used through OpenCode.

It is intentionally split into two layers:

1. `examples/deepseek-coding-agent.yaml` provides the model-independent workflow
   (`start -> plan -> execute -> verify -> self_review -> repair/handoff`).
2. `statem_deepseek.js` is an OpenCode plugin that injects the active StateM node
   into the model system prompt, preserves StateM state across compaction, and
   continues unfinished runs when an OpenCode session becomes idle.

The DeepSeek-specific policy follows the public StateM evaluation pattern: keep
base workflow semantics stable, add a bounded model-specific self-review layer,
prefer fresh consumer-facing evidence, and do not churn on an already-passing
candidate without concrete contradictory evidence.

## Requirements

- Python 3.11+
- StateM installed (`python3 -m pip install -e /path/to/statem`)
- OpenCode with its DeepSeek provider configured
- `deepseek-v4-flash` or `deepseek-v4-pro` selected in OpenCode

DeepSeek V4-Pro and V4-Flash use the same harness. The plugin auto-detects the
model ID and selects a `pro` or `flash` behavior profile. Override detection with:

```bash
export STATEM_DEEPSEEK_PROFILE=flash   # or pro, default: auto
```

## Install as an OpenCode plugin

Project-local:

```bash
mkdir -p .opencode/plugins .opencode/skills
ln -sfn /path/to/statem/integrations/opencode/statem_deepseek.js \
  .opencode/plugins/statem-deepseek.js
ln -sfn /path/to/statem/plugins/statem-deepseek/skills/statem-deepseek \
  .opencode/skills/statem-deepseek
```

Global:

```bash
mkdir -p ~/.config/opencode/plugins ~/.config/opencode/skills
ln -sfn /path/to/statem/integrations/opencode/statem_deepseek.js \
  ~/.config/opencode/plugins/statem-deepseek.js
ln -sfn /path/to/statem/plugins/statem-deepseek/skills/statem-deepseek \
  ~/.config/opencode/skills/statem-deepseek
```

OpenCode loads local plugins automatically from `.opencode/plugins/` and skills
from `.opencode/skills/`.

## Start a run

From the repository you want DeepSeek to work on:

```bash
cp /path/to/statem/examples/deepseek-coding-agent.yaml statem.yaml
statem validate statem.yaml
statem start statem.yaml --run-id my-task
opencode
```

Then ask OpenCode to use the `statem-deepseek` skill, or simply give it the task.
When an active `.statem` run exists, the plugin injects the current StateM state
on every DeepSeek turn.

## What the plugin enforces

### Per-turn state anchoring

For DeepSeek V4-Pro/Flash calls, `experimental.chat.system.transform` appends:

- current StateM node;
- legal outgoing states;
- current node prompt;
- the Flash/Pro review policy;
- the rule that transitions happen only through `statem goto`.

The text is merged into the first system block instead of creating a separate
system message.

### Auto-loop on `session.idle`

If OpenCode goes idle while a StateM run is still active and non-terminal, the
plugin sends a continuation prompt to the same session. It stops when:

- the StateM node is terminal (`handoff`, `done`, `complete`, etc.);
- there are no outgoing edges;
- the state fails to advance for three consecutive agent turns; or
- `STATEM_DEEPSEEK_MAX_CONTINUATIONS` is reached (default `12`).

The plugin never calls `statem goto` itself. The model remains responsible for
satisfying gates and explicitly moving the StateM pointer.

### Compaction

During OpenCode compaction the plugin adds a short reminder containing the
current StateM node and tells the resumed model to recover with `statem cur` and
`statem history`.

## Flash vs Pro

Both profiles use the same state graph and verification contract.

- **Flash** is biased toward narrow, tool-driven passes and early deterministic
  verification. It explicitly discourages repeated re-analysis after checks pass.
- **Pro** allows deeper architecture/review reasoning but retains the same bounded
  self-review rule so additional intelligence does not turn into unbounded churn.

Model selection and thinking/effort settings remain OpenCode/provider concerns;
this plugin does not rewrite the selected model or provider request parameters.

## Safety / cost controls

The auto-loop has two independent brakes:

```bash
export STATEM_DEEPSEEK_MAX_CONTINUATIONS=8
export STATEM_DEEPSEEK_PROFILE=flash
```

If the StateM entry does not change after three model turns, auto-loop pauses and
shows a warning toast rather than burning tokens indefinitely.
