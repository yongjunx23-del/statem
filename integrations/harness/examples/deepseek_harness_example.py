from __future__ import annotations

"""Reference StateM adapter for a DeepSeek-oriented agent harness.

This file intentionally depends only on StateM's public harness bridge contract.
Map the three methods below to the equivalent lifecycle callbacks in your host:

- before_turn(model_id)
- on_idle(model_id)
- on_compaction(model_id)

The surrounding harness remains responsible for actually calling DeepSeek and
for feeding a continuation prompt back into the same session.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from statem.harness_bridge import snapshot


@dataclass
class StateMHarnessAdapter:
    state_dir: Path = Path(".statem")
    profile: str = "auto"
    continuation_count: int = 0
    stagnant_turns: int = 0
    previous_entry_id: str | None = None

    def before_turn(self, model_id: str) -> str | None:
        """Return system text to append before a model turn, or None."""
        data = self._snapshot(model_id)
        if not data.get("managed"):
            return None
        self._observe_entry(data.get("entry_id"))
        return str(data.get("system_context") or "") or None

    def on_idle(self, model_id: str) -> dict[str, Any]:
        """Return a host-neutral stop/continue decision.

        A real harness should send `prompt` back to the same agent session when
        `decision == "continue"`.
        """
        data = self._snapshot(model_id)
        if not data.get("managed"):
            self.reset_loop()
            return {"decision": "stop", "reason": "no active StateM run"}

        limits = data.get("limits") or {}
        max_continuations = int(limits.get("max_continuations") or 12)
        max_stagnant = int(limits.get("max_stagnant_turns") or 3)
        continuation = data.get("continuation") or {}

        if continuation.get("decision") != "continue":
            self.reset_loop()
            return {"decision": "stop", "reason": "StateM run is terminal"}

        self._observe_entry(data.get("entry_id"))
        if self.stagnant_turns >= max_stagnant:
            return {
                "decision": "stop",
                "reason": (
                    f"StateM entry did not advance for {self.stagnant_turns} "
                    "continuation turns"
                ),
            }
        if self.continuation_count >= max_continuations:
            return {
                "decision": "stop",
                "reason": f"StateM continuation budget reached ({max_continuations})",
            }

        self.continuation_count += 1
        return {
            "decision": "continue",
            "prompt": str(continuation.get("prompt") or ""),
            "current": data.get("current"),
            "entry_id": data.get("entry_id"),
        }

    def on_compaction(self, model_id: str) -> str | None:
        """Return durable context the host should preserve during compaction."""
        data = self._snapshot(model_id)
        if not data.get("managed"):
            return None
        return str(data.get("compaction_context") or "") or None

    def reset_loop(self) -> None:
        self.continuation_count = 0
        self.stagnant_turns = 0
        self.previous_entry_id = None

    def _snapshot(self, model_id: str) -> dict[str, Any]:
        return snapshot(
            state_dir=self.state_dir.expanduser().resolve(),
            model=model_id,
            profile=self.profile,
        )

    def _observe_entry(self, entry_id: Any) -> None:
        entry = str(entry_id) if entry_id else None
        if entry is None:
            return
        if self.previous_entry_id is None:
            self.previous_entry_id = entry
            return
        if entry == self.previous_entry_id:
            self.stagnant_turns += 1
        else:
            self.previous_entry_id = entry
            self.stagnant_turns = 0


# Example host glue (pseudocode):
#
# adapter = StateMHarnessAdapter(profile="auto")
# model_id = "deepseek-v4-flash"
#
# system_append = adapter.before_turn(model_id)
# response = deepseek_harness.run_turn(
#     user_message,
#     system_append=system_append,
# )
#
# while deepseek_harness.is_idle(response):
#     decision = adapter.on_idle(model_id)
#     if decision["decision"] != "continue":
#         break
#     response = deepseek_harness.run_turn(decision["prompt"])
#
# if deepseek_harness.needs_compaction():
#     deepseek_harness.compact(extra_context=adapter.on_compaction(model_id))
