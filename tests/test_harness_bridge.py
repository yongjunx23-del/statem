from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from statem.core import RunOptions, StatemRuntime
from statem.harness_bridge import resolve_profile, snapshot


SPEC = """\
name: harness-bridge-test
initial: plan

nodes:
  plan:
    prompt: Plan the work.

  handoff:
    prompt: Hand off the result.

edges:
  - from: plan
    to: handoff
    condition: Planning is complete.
"""


class HarnessBridgeTest(unittest.TestCase):
    def test_profile_resolution_is_generic_by_default(self) -> None:
        self.assertEqual(resolve_profile("claude-sonnet", "auto"), "generic")
        self.assertEqual(
            resolve_profile("deepseek-v4-flash", "auto"), "deepseek-flash"
        )
        self.assertEqual(resolve_profile("deepseek-v4-pro", "auto"), "deepseek-pro")
        self.assertEqual(resolve_profile("anything", "flash"), "deepseek-flash")
        self.assertEqual(resolve_profile("anything", "pro"), "deepseek-pro")

    def test_snapshot_is_unmanaged_without_active_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data = snapshot(
                state_dir=Path(temp_dir) / ".statem",
                model="deepseek-v4-flash",
            )
        self.assertFalse(data["managed"])
        self.assertEqual(data["profile"], "deepseek-flash")

    def test_active_run_exports_host_neutral_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "statem.yaml"
            state_dir = root / ".statem"
            spec_path.write_text(SPEC, encoding="utf-8")
            runtime = StatemRuntime(
                RunOptions(state_dir=state_dir, json_mode=True, run_id="bridge-test")
            )
            runtime.start(str(spec_path))

            data = snapshot(state_dir=state_dir, model="deepseek-v4-flash")
            self.assertTrue(data["managed"])
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["profile"], "deepseek-flash")
            self.assertEqual(data["current"], "plan")
            self.assertEqual(data["next"], ["handoff"])
            self.assertFalse(data["terminal"])
            self.assertEqual(data["continuation"]["decision"], "continue")
            self.assertIn("StateM is the authoritative procedural state", data["system_context"])
            self.assertIn("DeepSeek V4-Flash execution profile", data["system_context"])
            self.assertTrue(data["entry_id"])
            self.assertGreater(data["limits"]["max_continuations"], 0)
            self.assertGreater(data["limits"]["max_stagnant_turns"], 0)

    def test_generic_profile_uses_same_state_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "statem.yaml"
            state_dir = root / ".statem"
            spec_path.write_text(SPEC, encoding="utf-8")
            StatemRuntime(
                RunOptions(state_dir=state_dir, json_mode=True, run_id="generic-test")
            ).start(str(spec_path))

            data = snapshot(state_dir=state_dir, model="some-other-model")
            self.assertEqual(data["profile"], "generic")
            self.assertIn("Generic harness execution profile", data["system_context"])
            self.assertEqual(data["current"], "plan")
            self.assertEqual(data["next"], ["handoff"])

    def test_terminal_state_returns_stop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec_path = root / "statem.yaml"
            state_dir = root / ".statem"
            spec_path.write_text(SPEC, encoding="utf-8")
            runtime = StatemRuntime(
                RunOptions(
                    state_dir=state_dir,
                    json_mode=True,
                    run_id="terminal-test",
                    yes=True,
                )
            )
            runtime.start(str(spec_path))
            runtime.goto("handoff")

            data = snapshot(state_dir=state_dir, model="deepseek-v4-pro")
            self.assertTrue(data["terminal"])
            self.assertEqual(data["continuation"]["decision"], "stop")
            self.assertEqual(data["continuation"]["prompt"], "")


if __name__ == "__main__":
    unittest.main()
