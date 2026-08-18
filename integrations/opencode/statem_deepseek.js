// Backward-compatible DeepSeek/OpenCode entry point.
//
// The real implementation is now host-generic and consumes the stable JSON
// contract from `python3 -m statem.harness_bridge`. Keep this filename so
// existing symlinks/installations continue to work.

import { StateMHarnessPlugin } from "./statem_harness.js"

export const StateMDeepSeekPlugin = StateMHarnessPlugin
