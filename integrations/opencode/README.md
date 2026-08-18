# StateM adapter for OpenCode

OpenCode is one example host for the host-neutral StateM harness bridge.

The reusable contract lives in:

```text
python3 -m statem.harness_bridge
```

and is documented in `integrations/harness/README.md`. The OpenCode plugin only
maps OpenCode lifecycle events onto that contract; it contains no DeepSeek-only
state-machine logic.

## Files

- `statem_harness.js` — generic OpenCode adapter;
- `statem_deepseek.js` — backward-compatible entry point for existing installs;
  it simply exports the generic adapter under the old DeepSeek plugin name.

## Install

Project-local:

```bash
mkdir -p .opencode/plugins .opencode/skills
ln -sfn /path/to/statem/integrations/opencode/statem_harness.js \
  .opencode/plugins/statem-harness.js
ln -sfn /path/to/statem/plugins/statem-harness/skills/statem-harness \
  .opencode/skills/statem-harness
```

Existing DeepSeek-specific symlinks may continue to point at
`statem_deepseek.js`; that path is kept as a compatibility wrapper.

Global:

```bash
mkdir -p ~/.config/opencode/plugins ~/.config/opencode/skills
ln -sfn /path/to/statem/integrations/opencode/statem_harness.js \
  ~/.config/opencode/plugins/statem-harness.js
ln -sfn /path/to/statem/plugins/statem-harness/skills/statem-harness \
  ~/.config/opencode/skills/statem-harness
```

## Behavior

Before a model turn, the adapter calls the bridge `snapshot` contract and appends
`system_context` when an active StateM run exists. The selected model ID is passed
to the bridge so `auto` can choose a model-specific profile when available.
DeepSeek V4-Flash/Pro therefore receive their reference profiles, while other
models receive the generic profile.

When OpenCode emits `session.idle`, the adapter consumes the bridge continuation
decision. It keeps an unfinished run moving in the same session but pauses when:

- StateM reaches a terminal state;
- the bridge returns `decision=stop`;
- the per-cycle continuation budget is exhausted; or
- the StateM `entry_id` remains unchanged for the configured stagnation limit.

During compaction it preserves the bridge `compaction_context`.

The adapter never runs `statem goto` itself.

## Configuration

Generic controls:

```bash
export STATEM_HARNESS_PROFILE=auto
export STATEM_HARNESS_MAX_CONTINUATIONS=12
export STATEM_HARNESS_MAX_STAGNANT_TURNS=3
```

If OpenCode cannot expose a model ID to a lifecycle event, the host can provide:

```bash
export STATEM_HARNESS_ASSUME_MODEL=deepseek-v4-flash
```

`STATEM_PYTHON` can select the Python executable used to invoke the bridge.

## DeepSeek example

For DeepSeek V4-Flash or V4-Pro, keep the shared runbook unchanged and let the
bridge select `deepseek-flash` or `deepseek-pro` from the model ID. See
`integrations/harness/examples/deepseek_harness_example.py` for the same pattern
expressed without any OpenCode API dependency.
