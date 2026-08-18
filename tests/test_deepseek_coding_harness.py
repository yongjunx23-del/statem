from __future__ import annotations

import unittest
from pathlib import Path

from statem.miniyaml import loads as yaml_loads


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "examples" / "deepseek-coding-agent.yaml"
GENERIC_PLUGIN = ROOT / "integrations" / "opencode" / "statem_harness.js"
DEEPSEEK_PLUGIN = ROOT / "integrations" / "opencode" / "statem_deepseek.js"
GENERIC_SKILL = ROOT / "plugins" / "statem-harness" / "skills" / "statem-harness" / "SKILL.md"
DEEPSEEK_SKILL = ROOT / "plugins" / "statem-deepseek" / "skills" / "statem-deepseek" / "SKILL.md"
BRIDGE = ROOT / "statem" / "harness_bridge.py"


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

    def test_generic_opencode_adapter_uses_bridge_and_autoloop(self) -> None:
        text = GENERIC_PLUGIN.read_text(encoding="utf-8")
        self.assertIn('"experimental.chat.system.transform"', text)
        self.assertIn('"experimental.session.compacting"', text)
        self.assertIn('event.type !== "session.idle"', text)
        self.assertIn("client.session.prompt", text)
        self.assertIn("statem.harness_bridge", text)
        self.assertIn("STATEM_HARNESS_PROFILE", text)
        self.assertIn("STATEM_HARNESS_ASSUME_MODEL", text)

    def test_deepseek_opencode_entry_is_only_a_compatibility_wrapper(self) -> None:
        text = DEEPSEEK_PLUGIN.read_text(encoding="utf-8")
        self.assertIn("StateMHarnessPlugin", text)
        self.assertIn("StateMDeepSeekPlugin", text)
        self.assertNotIn("session.idle", text)
        self.assertNotIn("deepseek-v4-flash", text.lower())

    def test_bridge_is_host_neutral_and_profiles_are_thin(self) -> None:
        bridge = BRIDGE.read_text(encoding="utf-8").lower()
        generic_skill = GENERIC_SKILL.read_text(encoding="utf-8").lower()
        deepseek_skill = DEEPSEEK_SKILL.read_text(encoding="utf-8").lower()
        self.assertIn("generic harness execution profile", bridge)
        self.assertIn("deepseek v4-flash execution profile", bridge)
        self.assertIn("deepseek v4-pro execution profile", bridge)
        self.assertIn("host-neutral", generic_skill)
        self.assertIn("reference profile", deepseek_skill)

    def test_public_packaging_is_not_benchmark_specific(self) -> None:
        combined = "\n".join(
            [
                RUNBOOK.read_text(encoding="utf-8"),
                GENERIC_PLUGIN.read_text(encoding="utf-8"),
                DEEPSEEK_PLUGIN.read_text(encoding="utf-8"),
                GENERIC_SKILL.read_text(encoding="utf-8"),
                DEEPSEEK_SKILL.read_text(encoding="utf-8"),
                BRIDGE.read_text(encoding="utf-8"),
            ]
        ).lower()
        self.assertIn("deepseek v4-flash", combined)
        self.assertIn("deepseek v4-pro", combined)
        self.assertNotIn("configure-git-webserver", combined)
        self.assertNotIn("terminal-bench", combined)


if __name__ == "__main__":
    unittest.main()
