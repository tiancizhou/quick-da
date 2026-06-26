import { createOpencode } from "@opencode-ai/sdk"
import fs from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const workerDir = path.dirname(fileURLToPath(import.meta.url))

process.env.PATH = [
  path.join(workerDir, "node_modules", ".bin"),
  process.env.PATH || ""
].join(path.delimiter)

async function readStdin() {
  const chunks = []
  for await (const chunk of process.stdin) {
    chunks.push(Buffer.from(chunk))
  }
  return Buffer.concat(chunks).toString("utf8")
}

const input = JSON.parse(await readStdin())
const workspace = path.resolve(input.workspace)
const prompt = input.prompt
const providerID = input.providerID || "quickda"
const modelID = input.modelID
const maxIdleMs = input.maxIdleMs || 8000
const maxRunMs = input.maxRunMs || 240000

function emit(event) {
  process.stdout.write(`${JSON.stringify(event)}\n`)
}

function emitOpencode(kind, payload = {}) {
  emit({ type: "opencode", kind, ...payload })
}

function providerConfig() {
  return {
    [providerID]: {
      name: providerID,
      npm: "@ai-sdk/openai-compatible",
      options: {
        baseURL: input.baseURL,
        apiKey: input.apiKey,
        timeout: input.timeoutMs || 300000
      },
      models: {
        [modelID]: {
          name: modelID,
          tool_call: true,
          attachment: false,
          reasoning: false,
          temperature: true,
          limit: {
            context: 128000,
            output: 16000
          }
        }
      }
    }
  }
}

function collectText(parts = []) {
  return parts
    .filter((part) => part && part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n")
}

function shortPath(file) {
  if (!file || typeof file !== "string") return "文件"
  const normalized = file.split(path.sep).join("/")
  const marker = "/opencode-workspace/"
  if (normalized.includes(marker)) {
    return normalized.slice(normalized.indexOf(marker) + marker.length)
  }
  if (normalized.startsWith("opencode-workspace/")) {
    return normalized.slice("opencode-workspace/".length)
  }
  const relative = path.relative(workspace, file)
  if (relative && !relative.startsWith("..") && !path.isAbsolute(relative)) {
    return relative.split(path.sep).join("/")
  }
  return path.basename(file)
}

function toolTitle(part) {
  const state = part?.state || {}
  if (state.title) {
    const title = shortPath(state.title)
    return title || "检查工作区"
  }
  if (part?.tool === "write") return `写入 ${shortPath(state.input?.filePath || state.input?.path)}`
  if (part?.tool === "edit") return `修改 ${shortPath(state.input?.filePath || state.input?.path)}`
  if (part?.tool === "patch") return "应用代码补丁"
  if (part?.tool === "read") return `读取 ${shortPath(state.input?.filePath || state.input?.path)}`
  if (part?.tool === "list" || part?.tool === "glob") return "查看项目文件"
  if (part?.tool === "grep") return "搜索项目代码"
  return part?.tool ? "执行代码生成步骤" : "执行智能体步骤"
}

function compactToolInput(input = {}) {
  const compact = {}
  if (input.filePath || input.path) compact.filePath = shortPath(input.filePath || input.path)
  if (Array.isArray(input.todos)) compact.todos = input.todos
  if (input.pattern) compact.pattern = input.pattern
  if (input.command) compact.command = input.command
  return compact
}

async function hasStaticEntry() {
  try {
    const stat = await fs.stat(path.join(workspace, "index.html"))
    return stat.isFile() && stat.size > 0
  } catch {
    return false
  }
}

const config = {
  share: "disabled",
  autoupdate: false,
  model: `${providerID}/${modelID}`,
  provider: providerConfig(),
  agent: {
    build: {
      tools: {
        write: true,
        edit: true,
        patch: true,
        read: true,
        list: true,
        glob: true,
        grep: true,
        bash: false
      }
    }
  }
}

let opencode
let streamAbort
try {
  opencode = await createOpencode({
    hostname: "127.0.0.1",
    port: 0,
    timeout: 20000,
    config
  })
  const { client } = opencode
  const sessionResult = await client.session.create({
    query: { directory: workspace },
    body: { title: "QuickDa generated frontend" }
  })
  const session = sessionResult.data
  if (!session?.id) {
    throw new Error("OpenCode did not return a session id")
  }

  emitOpencode("session", {
    sessionID: session.id,
    providerID,
    modelID,
    agent: "build"
  })

  streamAbort = new AbortController()
  const seenTools = new Map()
  const seenFileEvents = new Map()
  const assistantMessageIDs = new Set()
  const announcedAssistantMessages = new Set()
  let lastActivity = Date.now()
  let idle = false
  let capturedError = null
  let lastTextByPart = new Map()

  const eventStream = await client.global.event({ signal: streamAbort.signal })
  const eventTask = (async () => {
    for await (const event of eventStream.stream) {
      const payload = event?.payload
      if (!payload) continue
      if (payload.properties?.sessionID && payload.properties.sessionID !== session.id) continue
      if (payload.properties?.part?.sessionID && payload.properties.part.sessionID !== session.id) continue
      if (payload.properties?.info?.sessionID && payload.properties.info.sessionID !== session.id) continue

      lastActivity = Date.now()

      if (payload.type === "message.updated") {
        const info = payload.properties.info
        if (info?.role === "assistant") {
          assistantMessageIDs.add(info.id)
          if (!announcedAssistantMessages.has(info.id)) {
            announcedAssistantMessages.add(info.id)
            emitOpencode("assistant_start", {
              sessionID: session.id,
              messageID: info.id,
              providerID: info.providerID,
              modelID: info.modelID,
              cost: info.cost,
              tokens: info.tokens
            })
          }
        }
      } else if (payload.type === "message.part.updated") {
        const part = payload.properties.part
        if (part.type === "text") {
          if (!assistantMessageIDs.has(part.messageID)) continue
          const previous = lastTextByPart.get(part.id) || ""
          const text = typeof payload.properties.delta === "string"
            ? payload.properties.delta
            : String(part.text || "").slice(previous.length)
          lastTextByPart.set(part.id, String(part.text || ""))
          if (text) {
            emitOpencode("assistant_delta", {
              sessionID: session.id,
              messageID: part.messageID,
              partID: part.id,
              content: text
            })
          }
        } else if (part.type === "tool") {
          if (!assistantMessageIDs.has(part.messageID)) continue
          const key = `${part.callID}:${part.state?.status || ""}`
          if (!seenTools.has(key)) {
            seenTools.set(key, true)
            const label = toolTitle(part)
            if (part.state?.status === "running") emit({ type: "progress", content: `${label}...` })
            emitOpencode("tool", {
              sessionID: session.id,
              messageID: part.messageID,
              callID: part.callID,
              tool: part.tool,
              status: part.state?.status || "unknown",
              title: label,
              input: compactToolInput(part.state?.input || {}),
              error: part.state?.error || null
            })
          }
        } else if (part.type === "patch" && part.files?.length) {
          emitOpencode("patch", {
            sessionID: session.id,
            messageID: part.messageID,
            files: part.files.map(shortPath)
          })
        } else if (part.type === "step-start") {
          emit({ type: "progress", content: "OpenCode 正在执行下一步..." })
          emitOpencode("step", {
            sessionID: session.id,
            messageID: part.messageID,
            status: "start"
          })
        } else if (part.type === "step-finish") {
          emitOpencode("step", {
            sessionID: session.id,
            messageID: part.messageID,
            status: "finish",
            reason: part.reason,
            cost: part.cost,
            tokens: part.tokens
          })
        }
      } else if (payload.type === "file.edited" || payload.type === "file.watcher.updated") {
        const file = shortPath(payload.properties.file)
        const now = Date.now()
        if (now - (seenFileEvents.get(file) || 0) > 1200) {
          seenFileEvents.set(file, now)
          emitOpencode("file", {
            sessionID: session.id,
            file,
            event: payload.properties.event || "edited"
          })
        }
      } else if (payload.type === "todo.updated") {
        const active = payload.properties.todos?.find((todo) => todo.status === "in_progress")
        if (active?.content) emit({ type: "progress", content: active.content })
        emitOpencode("todo", {
          sessionID: session.id,
          todos: payload.properties.todos || []
        })
      } else if (payload.type === "permission.updated") {
        const permission = payload.properties
        emit({ type: "progress", content: `OpenCode 请求权限：${permission.title || permission.type}` })
        emitOpencode("permission", {
          sessionID: session.id,
          permissionID: permission.id,
          permissionType: permission.type,
          title: permission.title
        })
        try {
          await client.postSessionIdPermissionsPermissionId({
            path: { id: session.id, permissionID: permission.id },
            query: { directory: workspace },
            body: { response: "once" }
          })
        } catch (error) {
          emitOpencode("error", {
            sessionID: session.id,
            message: `Permission reply failed: ${error instanceof Error ? error.message : String(error)}`
          })
        }
      } else if (payload.type === "session.error") {
        capturedError = payload.properties.error?.data?.message || payload.properties.error?.name || "OpenCode session error"
        emitOpencode("error", {
          sessionID: session.id,
          message: capturedError
        })
      } else if (payload.type === "session.status") {
        emitOpencode("status", {
          sessionID: session.id,
          status: payload.properties.status
        })
      } else if (payload.type === "session.idle") {
        emitOpencode("status", {
          sessionID: session.id,
          status: { type: "idle" }
        })
        idle = true
        break
      }
    }
  })()

  await client.session.promptAsync({
    path: { id: session.id },
    query: { directory: workspace },
    body: {
      agent: "build",
      model: { providerID, modelID },
      tools: {
        write: true,
        edit: true,
        patch: true,
        read: true,
        list: true,
        glob: true,
        grep: true,
        bash: false
      },
      parts: [{ type: "text", text: prompt }]
    }
  })

  const started = Date.now()
  while (!idle) {
    if (Date.now() - started > maxRunMs) {
      emitOpencode("status", {
        sessionID: session.id,
        status: { type: "timeout" }
      })
      break
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }

  streamAbort.abort()
  await eventTask.catch(() => {})

  if (capturedError && !(await hasStaticEntry())) {
    throw new Error(capturedError)
  }

  process.stdout.write(JSON.stringify({
    type: "result",
    ok: true,
    sessionID: session.id,
    text: ""
  }) + "\n")
} catch (error) {
  process.stdout.write(JSON.stringify({
    type: "result",
    ok: false,
    error: error instanceof Error ? error.message : String(error)
  }) + "\n")
  process.exitCode = 1
} finally {
  streamAbort?.abort()
  opencode?.server?.close()
}
