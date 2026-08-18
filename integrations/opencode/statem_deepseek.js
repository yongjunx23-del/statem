import { existsSync } from "node:fs"
import { resolve } from "node:path"
import { spawnSync } from "node:child_process"

const TERMINAL_STATES = new Set(["handoff", "done", "complete", "completed", "finished"])
const runningSessions = new Set()
const sessionProfiles = new Map()

function stateDirFor(directory) {
  const raw = process.env.STATEM_STATE_DIR || ".statem"
  return resolve(directory, raw)
}

function runStatem(directory, stateDir, command) {
  const args = [command, "--state-dir", stateDir, "--json"]
  const configured = process.env.STATEM_COMMAND
  let result

  if (configured) {
    result = spawnSync(configured, args, {
      cwd: directory,
      encoding: "utf8",
      timeout: 12_000,
    })
  } else {
    result = spawnSync("statem", args, {
      cwd: directory,
      encoding: "utf8",
      timeout: 12_000,
    })
    if (result.error?.code === "ENOENT") {
      result = spawnSync("python3", ["-m", "statem", ...args], {
        cwd: directory,
        encoding: "utf8",
        timeout: 12_000,
      })
    }
  }

  if (result.error || result.status !== 0 || !result.stdout?.trim()) return null
  try {
    return JSON.parse(result.stdout)
  } catch {
    return null
  }
}

function readCurrent(directory) {
  const stateDir = stateDirFor(directory)
  if (!existsSync(resolve(stateDir, "active_run"))) return null
  return runStatem(directory, stateDir, "cur")
}

function modelId(model) {
  return String(model?.id || model?.modelID || model?.modelId || "")
}

function configuredProfile() {
  const forced = String(process.env.STATEM_DEEPSEEK_PROFILE || "auto").toLowerCase()
  return forced === "flash" || forced === "pro" ? forced : null
}

function chooseProfile(model) {
  const forced = configuredProfile()
  if (forced) return forced
  if (String(process.env.STATEM_DEEPSEEK_PROFILE || "auto").toLowerCase() !== "auto") return null

  const id = modelId(model).toLowerCase()
  if (!id.includes("deepseek")) return null
  if (id.includes("v4-pro") || id.endsWith("pro")) return "pro"
  if (id.includes("v4-flash") || id.endsWith("flash")) return "flash"
  return null
}

function profilePolicy(profile) {
  if (profile === "pro") {
    return [
      "DeepSeek V4-Pro profile:",
      "- Use deep reasoning for architecture, ambiguous failures, and review, but keep the execution loop evidence-driven.",
      "- Prefer deterministic verification over repeated speculative analysis.",
      "- During self_review, run at most one bounded countercheck unless a concrete failing check creates new evidence.",
      "- A passing candidate should not be rewritten without concrete contradictory evidence.",
    ].join("\n")
  }
  return [
    "DeepSeek V4-Flash profile:",
    "- Keep each pass narrow, concrete, and tool-driven; avoid re-deriving the whole solution after every step.",
    "- Prefer deterministic verification over extra reflection, especially after tests already pass.",
    "- During self_review, run at most one bounded countercheck, then choose repair or handoff.",
    "- If a hard ambiguity survives repeated repair, record the blocker instead of churning indefinitely.",
  ].join("\n")
}

function nextNames(cur) {
  return (cur?.next || [])
    .map((edge) => (edge && typeof edge === "object" ? edge.to : null))
    .filter(Boolean)
}

function stateContext(cur, profile) {
  const next = nextNames(cur)
  const gateSummary = Array.isArray(cur?.before_transfer)
    ? cur.before_transfer.map((item) => item?.type || "check").join(", ")
    : "none"
  return [
    "StateM is the authoritative procedural state for this coding run.",
    `Current state: ${cur.current}`,
    `Allowed next states: ${next.length ? next.join(", ") : "(none)"}`,
    `Current transition gates: ${gateSummary}`,
    cur.prompt ? `Current state instructions:\n${cur.prompt}` : "",
    "Move state only with `statem goto <next-state>`. Do not claim completion before a terminal handoff state.",
    "When a concrete task reveals a new regression check, register it as a StateM dynamic check rather than relying on memory.",
    profilePolicy(profile),
  ]
    .filter(Boolean)
    .join("\n\n")
}

function continuationPrompt(cur, profile) {
  return [
    "Continue the active StateM-managed run instead of stopping.",
    `Current state: ${cur.current}`,
    `Allowed next states: ${nextNames(cur).join(", ") || "(none)"}`,
    "First run `statem cur --json` and follow the current node prompt.",
    "Do the work required by the current state, then transition only with `statem goto <next-state>`.",
    "If a gate fails, repair the concrete failure and retry. If user input is genuinely required, explain the blocker and stop rather than inventing an answer.",
    profilePolicy(profile),
  ].join("\n")
}

function maxContinuations() {
  const parsed = Number.parseInt(process.env.STATEM_DEEPSEEK_MAX_CONTINUATIONS || "12", 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 12
}

export const StateMDeepSeekPlugin = async ({ client, directory }) => {
  return {
    "experimental.chat.system.transform": async (input, output) => {
      const profile = chooseProfile(input.model)
      if (!profile) return
      const cur = readCurrent(directory)
      if (!cur) return
      if (input.sessionID) sessionProfiles.set(input.sessionID, profile)

      const context = stateContext(cur, profile)
      if (!Array.isArray(output.system)) return
      if (output.system.length === 0) output.system.push(context)
      else output.system[0] = `${output.system[0]}\n\n${context}`
    },

    "experimental.session.compacting": async (input, output) => {
      if (!sessionProfiles.has(input.sessionID) && !configuredProfile()) return
      const cur = readCurrent(directory)
      if (!cur || !Array.isArray(output.context)) return
      output.context.push(
        `Preserve StateM durable state across compaction. Current=${cur.current}; next=${nextNames(cur).join(",") || "none"}. After compaction run statem cur --json and statem history --tail 10 --json before continuing.`,
      )
    },

    event: async ({ event }) => {
      if (event.type === "session.deleted") {
        const sessionID = event.properties?.info?.id || event.properties?.sessionID
        if (sessionID) {
          sessionProfiles.delete(sessionID)
          runningSessions.delete(sessionID)
        }
        return
      }
      if (event.type !== "session.idle") return
      const sessionID = event.properties?.sessionID
      if (!sessionID || runningSessions.has(sessionID)) return

      const activeProfile = sessionProfiles.get(sessionID) || configuredProfile()
      if (!activeProfile) return
      const cur0 = readCurrent(directory)
      if (!cur0) return
      if (TERMINAL_STATES.has(cur0.current) || nextNames(cur0).length === 0) return

      runningSessions.add(sessionID)
      try {
        let stagnant = 0
        let previousEntry = cur0.current_entry_id || `${cur0.current}:${JSON.stringify(nextNames(cur0))}`

        for (let step = 0; step < maxContinuations(); step += 1) {
          const cur = readCurrent(directory)
          if (!cur || TERMINAL_STATES.has(cur.current) || nextNames(cur).length === 0) break

          await client.session.prompt({
            path: { id: sessionID },
            body: {
              parts: [{ type: "text", text: continuationPrompt(cur, activeProfile) }],
            },
          })

          const after = readCurrent(directory)
          if (!after || TERMINAL_STATES.has(after.current) || nextNames(after).length === 0) break
          const entry = after.current_entry_id || `${after.current}:${JSON.stringify(nextNames(after))}`
          stagnant = entry === previousEntry ? stagnant + 1 : 0
          previousEntry = entry
          if (stagnant >= 2) {
            await client.tui?.showToast?.({
              body: {
                title: "StateM DeepSeek",
                message: `Auto-loop paused in ${after.current}: state did not advance after 3 turns.`,
                variant: "warning",
              },
            })
            break
          }
        }
      } catch (error) {
        await client.app?.log?.({
          body: {
            service: "statem-deepseek",
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
