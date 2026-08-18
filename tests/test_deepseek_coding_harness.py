from __future__ import annotations

import unittest
from pathlib import Path

from statem.miniyaml import loads as yaml_loads


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "examples" / "deepseek-coding-agent.yaml"
PLUGIN = ROOT / "integrations" / "opencode" / "statem_deepseek.js"
SKILL = ROOT / "plugins" / "statem-deepseek" / "skills" / "statem-deepseek" / "SKILL.md"


class DeepSeekCodingHarnessTest(unittest.TestCase):
    def test_runbook_has_bounded_review_and_repair_loop(self) -> None:
        spec = yaml_loads(RUNBOOK.read_text(encoding="utf-8"))
        self.assertEqual(spec["initial"], "start")
        self.assertEqual(
            set(spec["nodes"]),
            {"start", "plan", "execute", "verify", "self_review", "repair", "handoff"},
        )
        edges = {(edge["from"], edge["to"]) for edge in spec["edges"]}
        self.assertIn(("verify", "repair"), edges)
        self.assertIn(("verify", "self_review"), edges)
        self.assertIn(("self_review", "repair"), edges)
        self.assertIn(("self_review", "handoff"), edges)
        self.assertIn(("repair", "verify"), edges)
        review_prompt = spec["nodes"]["self_review"]["prompt"]
        self.assertIn("one bounded review pass", review_prompt)
        self.assertIn("concrete contradictory evidence", review_prompt)

    def test_runbook_has_no_manual_gate(self) -> None:
        spec = yaml_loads(RUNBOOK.read_text(encoding="utf-8"))
        for node in spec["nodes"].values():
            checks = node.get("before_transfer", [])
            if isinstance(checks, dict):
                checks = [checks]
            self.assertNotIn("manual", {check.get("type") for check in checks})

    def test_opencode_plugin_contains_state_anchor_and_autoloop(self) -> None:
        text = PLUGIN.read_text(encoding="utf-8")
        self.assertIn('"experimental.chat.system.transform"', text)
        self.assertIn('"experimental.session.compacting"', text)
        self.assertIn('event.type !== "session.idle"', text)
        self.assertIn("client.session.prompt", text)
        self.assertIn("STATEM_DEEPSEEK_PROFILE", text)
        self.assertIn("STATEM_DEEPSEEK_MAX_CONTINUATIONS", text)
        self.assertIn("statem goto <next-state>", text)

    def test_public_packaging_is_model_specific_not_benchmark_specific(self) -> None:
        combined = "\n".join(
            [
                RUNBOOK.read_text(encoding="utf-8"),
                PLUGIN.read_text(encoding="utf-8"),
                SKILL.read_text(encoding="utf-8"),
            ]
        ).lower()
        self.assertIn("deepseek v4-flash", combined)
        self.assertIn("deepseek v4-pro", combined)
        self.assertNotIn("configure-git-webserver", combined)
        self.assertNotIn("terminal-bench", combined)


if __name__ == "__main__":
    unittest.main()
