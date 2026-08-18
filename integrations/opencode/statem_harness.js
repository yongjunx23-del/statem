import { spawnSync } from "node:child_process"

const runningSessions = new Set()
const sessionModels = new Map()

function modelId(model) {
  return String(model?.id || model?.modelID || model?.modelId || "")
}

function stateDirFor(directory) {
  return process.env.STATEM_STATE_DIR || `${directory}/.statem`
}

function bridgeSnapshot(directory, model) {
  const python = process.env.STATEM_PYTHON || "python3"
  const profile = process.env.STATEM_HARNESS_PROFILE || "auto"
  const args = [
    "-m",
    "statem.harness_bridge",
    "snapshot",
    "--state-dir",
    stateDirFor(directory),
    "--model",
    model || "",
    "--profile",
    profile,
  ]
  const result = spawnSync(python, args, {
    cwd: directory,
    encoding: "utf8",
    timeout: 12_000,
  })
  if (result.error || result.status !== 0 || !result.stdout?.trim()) return null
  try {
    return JSON.parse(result.stdout)
  } catch {
    return null
  }
}

function forcedModel() {
  return String(process.env.STATEM_HARNESS_ASSUME_MODEL || "")
}

export const StateMHarnessPlugin = async ({ client, directory }) => {
  return {
    "experimental.chat.system.transform": async (input, output) => {
      const model = modelId(input.model)
      const data = bridgeSnapshot(directory, model)
      if (!data?.managed) return

      if (input.sessionID) sessionModels.set(input.sessionID, model)
      const context = String(data.system_context || "")
      if (!context || !Array.isArray(output.system)) return
      if (output.system.length === 0) output.system.push(context)
      else output.system[0] = `${output.system[0]}\n\n${context}`
    },

    "experimental.session.compacting": async (input, output) => {
      const sessionID = input?.sessionID
      const model = (sessionID && sessionModels.get(sessionID)) || forcedModel()
      if (!model) return
      const data = bridgeSnapshot(directory, model)
      if (!data?.managed || !Array.isArray(output.context)) return
      const context = String(data.compaction_context || "")
      if (context) output.context.push(context)
    },

    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      const sessionID = event.properties?.sessionID
      if (!sessionID || runningSessions.has(sessionID)) return

      const model = sessionModels.get(sessionID) || forcedModel()
      if (!model) return
      let data = bridgeSnapshot(directory, model)
      if (!data?.managed || data.terminal || data.continuation?.decision !== "continue") return

      runningSessions.add(sessionID)
      try {
        let previousEntry = data.entry_id || null
        let stagnant = 0
        const maxContinuations = Number(data.limits?.max_continuations || 12)
        const maxStagnant = Number(data.limits?.max_stagnant_turns || 3)

        for (let step = 0; step < maxContinuations; step += 1) {
          if (!data?.managed || data.terminal || data.continuation?.decision !== "continue") break

          await client.session.prompt({
            path: { id: sessionID },
            body: {
              parts: [{ type: "text", text: String(data.continuation?.prompt || "") }],
            },
          })

          data = bridgeSnapshot(directory, model)
          if (!data?.managed || data.terminal || data.continuation?.decision !== "continue") break

          const entry = data.entry_id || null
          if (entry && previousEntry && entry === previousEntry) stagnant += 1
          else stagnant = 0
          previousEntry = entry

          if (stagnant >= maxStagnant) {
            await client.tui?.showToast?.({
              body: {
                title: "StateM Harness",
                message: `Auto-loop paused in ${data.current}: StateM entry did not advance.`,
                variant: "warning",
              },
            })
            break
          }
        }
      } catch (error) {
        await client.app?.log?.({
          body: {
            service: "statem-harness",
            level: "warn",
            message: `Auto-loop stopped: ${error instanceof Error ? error.message : String(error)}`,
          },
        })
      } finally {
        runningSessions.delete(sessionID)
      }
    },
  }
}
