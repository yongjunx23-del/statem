from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .core import RunOptions, StatemError, StatemRuntime


DEFAULT_TERMINAL_STATES = {"handoff", "done", "complete", "completed", "finished"}
PROFILE_NAMES = {"auto", "generic", "deepseek-flash", "deepseek-pro"}


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _terminal_states() -> set[str]:
    raw = os.environ.get("STATEM_HARNESS_TERMINAL_STATES")
    if not raw:
        return DEFAULT_TERMINAL_STATES
    return {part.strip() for part in raw.split(",") if part.strip()}


def resolve_profile(model: str, requested: str = "auto") -> str:
    requested = (requested or "auto").strip().lower()
    legacy = os.environ.get("STATEM_DEEPSEEK_PROFILE")
    configured = os.environ.get("STATEM_HARNESS_PROFILE") or legacy
    if requested == "auto" and configured:
        requested = configured.strip().lower()

    aliases = {
        "flash": "deepseek-flash",
        "pro": "deepseek-pro",
        "deepseek_v4_flash": "deepseek-flash",
        "deepseek_v4_pro": "deepseek-pro",
    }
    requested = aliases.get(requested, requested)
    if requested not in PROFILE_NAMES:
        raise ValueError(f"unknown harness profile: {requested}")
    if requested != "auto":
        return requested

    model_id = (model or "").lower()
    if "deepseek" in model_id and ("v4-pro" in model_id or model_id.endswith("pro")):
        return "deepseek-pro"
    if "deepseek" in model_id and ("v4-flash" in model_id or model_id.endswith("flash")):
        return "deepseek-flash"
    return "generic"


def profile_policy(profile: str) -> str:
    if profile == "deepseek-pro":
        return "\n".join(
            [
                "DeepSeek V4-Pro execution profile:",
                "- Use deeper reasoning for architecture, ambiguous failures, and review, while keeping the loop evidence-driven.",
                "- Prefer deterministic verification over repeated speculative analysis.",
                "- During self-review, use at most one bounded countercheck unless a concrete failing check creates new evidence.",
                "- Do not rewrite a passing candidate without concrete contradictory evidence.",
            ]
        )
    if profile == "deepseek-flash":
        return "\n".join(
            [
                "DeepSeek V4-Flash execution profile:",
                "- Keep each pass narrow, concrete, and tool-driven; do not re-derive the whole solution after every step.",
                "- Prefer early deterministic verification, especially after a local edit.",
                "- During self-review, use at most one bounded countercheck, then choose repair or handoff.",
                "- If a hard ambiguity survives repeated repair, record the blocker instead of churning indefinitely.",
            ]
        )
    return "\n".join(
        [
            "Generic harness execution profile:",
            "- Treat StateM as procedural state, not as extra prose to ignore.",
            "- Prefer fresh deterministic evidence over repeated self-reflection.",
            "- Keep review bounded; new work should be triggered by concrete evidence or an unmet acceptance condition.",
            "- Preserve passing behavior unless a real contradiction or regression is found.",
        ]
    )


def _next_names(cur: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for edge in cur.get("next") or []:
        if isinstance(edge, dict) and edge.get("to"):
            result.append(str(edge["to"]))
    return result


def _gate_summary(cur: dict[str, Any]) -> str:
    gates = cur.get("before_transfer") or []
    names = [str(item.get("type") or "check") for item in gates if isinstance(item, dict)]
    return ", ".join(names) if names else "none"


def _system_context(cur: dict[str, Any], profile: str) -> str:
    next_states = _next_names(cur)
    return "\n\n".join(
        part
        for part in [
            "StateM is the authoritative procedural state for this agent run.",
            f"Current state: {cur.get('current')}",
            f"Allowed next states: {', '.join(next_states) if next_states else '(none)'}",
            f"Current transition gates: {_gate_summary(cur)}",
            f"Current state instructions:\n{cur.get('prompt')}" if cur.get("prompt") else "",
            "Move state only with `statem goto <next-state>`. Do not claim completion before a terminal handoff state.",
            "When a concrete task reveals a new regression condition, register it as a StateM dynamic check rather than relying on memory.",
            profile_policy(profile),
        ]
        if part
    )


def _continuation_prompt(cur: dict[str, Any], profile: str) -> str:
    next_states = _next_names(cur)
    return "\n".join(
        [
            "Continue the active StateM-managed run instead of stopping.",
            f"Current state: {cur.get('current')}",
            f"Allowed next states: {', '.join(next_states) if next_states else '(none)'}",
            "First inspect `statem cur --json` and follow the current node prompt.",
            "Do the work required by the current state, then transition only with `statem goto <next-state>`.",
            "If a gate fails, repair the concrete failure and retry. If genuine user input is required, report the blocker rather than inventing an answer.",
            profile_policy(profile),
        ]
    )


def _compaction_context(cur: dict[str, Any]) -> str:
    next_states = _next_names(cur)
    return (
        "Preserve StateM durable state across context compaction. "
        f"Current={cur.get('current')}; next={','.join(next_states) if next_states else 'none'}. "
        "After compaction, recover with `statem cur --json` and `statem history --tail 10 --json` before continuing."
    )


def snapshot(*, state_dir: Path, model: str = "", profile: str = "auto") -> dict[str, Any]:
    resolved_profile = resolve_profile(model, profile)
    runtime = StatemRuntime(RunOptions(state_dir=state_dir, json_mode=True))
    try:
        cur = runtime.cur()
    except StatemError as exc:
        return {
            "schema_version": 1,
            "managed": False,
            "profile": resolved_profile,
            "model": model,
            "reason": str(exc),
            "limits": {
                "max_continuations": _positive_int("STATEM_HARNESS_MAX_CONTINUATIONS", 12),
                "max_stagnant_turns": _positive_int("STATEM_HARNESS_MAX_STAGNANT_TURNS", 3),
            },
        }

    next_states = _next_names(cur)
    current = str(cur.get("current") or "")
    terminal = current in _terminal_states() or not next_states
    return {
        "schema_version": 1,
        "managed": True,
        "profile": resolved_profile,
        "model": model,
        "run_id": cur.get("run_id"),
        "current": current,
        "entry_id": cur.get("current_entry_id"),
        "next": next_states,
        "terminal": terminal,
        "system_context": _system_context(cur, resolved_profile),
        "continuation": {
            "decision": "stop" if terminal else "continue",
            "prompt": "" if terminal else _continuation_prompt(cur, resolved_profile),
        },
        "compaction_context": _compaction_context(cur),
        "limits": {
            "max_continuations": _positive_int("STATEM_HARNESS_MAX_CONTINUATIONS", 12),
            "max_stagnant_turns": _positive_int("STATEM_HARNESS_MAX_STAGNANT_TURNS", 3),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m statem.harness_bridge",
        description="Host-neutral JSON bridge between StateM and agent harnesses.",
    )
    parser.add_argument(
        "command",
        choices=("snapshot", "context", "decision", "compact"),
        help="JSON view required by the host integration point",
    )
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("STATEM_STATE_DIR", ".statem"),
        help="StateM runtime directory",
    )
    parser.add_argument("--model", default="", help="host model identifier")
    parser.add_argument(
        "--profile",
        default="auto",
        help="auto, generic, deepseek-flash, or deepseek-pro",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        data = snapshot(
            state_dir=Path(args.state_dir).expanduser().resolve(),
            model=args.model,
            profile=args.profile,
        )
    except ValueError as exc:
        print(json.dumps({"schema_version": 1, "managed": False, "error": str(exc)}))
        return 2

    if args.command == "context":
        payload = {
            "schema_version": data["schema_version"],
            "managed": data["managed"],
            "profile": data.get("profile"),
            "current": data.get("current"),
            "entry_id": data.get("entry_id"),
            "terminal": data.get("terminal"),
            "system_context": data.get("system_context", ""),
        }
    elif args.command == "decision":
        payload = {
            "schema_version": data["schema_version"],
            "managed": data["managed"],
            "profile": data.get("profile"),
            "current": data.get("current"),
            "entry_id": data.get("entry_id"),
            "terminal": data.get("terminal"),
            "continuation": data.get("continuation", {"decision": "stop", "prompt": ""}),
            "limits": data.get("limits", {}),
        }
    elif args.command == "compact":
        payload = {
            "schema_version": data["schema_version"],
            "managed": data["managed"],
            "current": data.get("current"),
            "entry_id": data.get("entry_id"),
            "compaction_context": data.get("compaction_context", ""),
        }
    else:
        payload = data

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
