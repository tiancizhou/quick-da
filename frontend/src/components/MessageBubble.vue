<template>
  <div class="bubble-row" :class="role === 'user' ? 'bubble-row--user' : 'bubble-row--assistant'">
    <div class="bubble" :class="[role === 'user' ? 'bubble--user' : 'bubble--assistant', { 'bubble--opencode': isOpenCodeTranscript }]">
      <div v-if="isOpenCodeTranscript" class="opencode-chat">
        <div class="opencode-chat__topbar">
          <div class="opencode-chat__identity">
            <span class="opencode-chat__mark" />
            <div>
              <strong>OpenCode Agent</strong>
              <span>{{ opencodeMeta }}</span>
            </div>
          </div>
          <div class="opencode-chat__badges">
            <span class="opencode-chat__badge">{{ sourceModeLabel }}</span>
            <span class="opencode-chat__state">{{ runState }}</span>
          </div>
        </div>

        <div class="opencode-chat__grid">
          <section class="opencode-chat__assistant-pane">
            <div class="opencode-chat__pane-head">
              <span>assistant</span>
              <small>{{ assistantText ? "实时回复" : "等待模型输出" }}</small>
            </div>
            <div v-if="assistantText" class="opencode-chat__assistant">{{ assistantText }}</div>
            <div v-else class="opencode-chat__assistant opencode-chat__assistant--muted">
              OpenCode 正在读取上下文、规划 React 前端源码并操作工作区。
            </div>
          </section>

          <aside class="opencode-chat__run-pane">
            <div v-if="todoItems.length" class="opencode-chat__section">
              <div class="opencode-chat__section-title">计划</div>
              <div class="opencode-chat__todo-list">
                <div v-for="todo in todoItems" :key="todo.content" class="opencode-chat__todo-item" :class="`opencode-chat__todo-item--${todo.status}`">
                  <span />
                  <p>{{ todo.content }}</p>
                </div>
              </div>
            </div>

            <div class="opencode-chat__section">
              <div class="opencode-chat__section-title">执行</div>
              <div v-if="timelineItems.length" class="opencode-chat__timeline">
                <div v-for="item in timelineItems" :key="item.id" class="opencode-chat__event" :class="`opencode-chat__event--${item.status}`">
                  <span class="opencode-chat__event-dot" />
                  <div>
                    <strong>{{ item.title }}</strong>
                    <code v-if="item.detail">{{ item.detail }}</code>
                  </div>
                </div>
              </div>
              <div v-else class="opencode-chat__empty-run">
                正在等待 OpenCode 事件流...
              </div>
            </div>
          </aside>
        </div>
      </div>
      <span v-else-if="role === 'assistant' && !content" class="bubble__placeholder">
        <span class="bubble__dot" />
        正在生成项目文件...
      </span>
      <div v-else-if="isCodeStream" class="bubble__code-shell">
        <div class="bubble__code-header">
          <span class="bubble__code-dot" />
          正在生成项目文件
        </div>
        <pre ref="codeStreamRef" class="bubble__code-stream">{{ content }}</pre>
      </div>
      <span v-else class="bubble__content">{{ content }}</span>
    </div>

    <details v-if="role === 'assistant' && resultStatus" class="result-panel" :open="resultStatus !== 'active'">
      <summary class="result-panel__summary">
        <span class="result-panel__status" :class="`result-panel__status--${resultStatus}`" />
        <span class="result-panel__title">{{ resultTitle }}</span>
        <span class="result-panel__toggle">{{ resultStatus === 'active' ? '展开' : '收起' }}</span>
      </summary>

      <div class="result-panel__body">
        <p>{{ resultDescription }}</p>
        <p v-if="resultError && resultStatus !== 'active'" class="result-panel__error">{{ resultError }}</p>
        <div v-if="resultUrl && resultStatus === 'active'" class="result-panel__actions">
          <a :href="resultUrl" target="_blank" rel="noopener noreferrer" class="result-panel__btn result-panel__btn--primary">
            预览应用
          </a>
          <button type="button" class="result-panel__btn" @click="copyResultUrl">
            {{ copyButtonText }}
          </button>
          <a :href="resultUrl" target="_blank" rel="noopener noreferrer" class="result-panel__btn">
            新窗口打开
          </a>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"
import type { OpenCodeStreamEvent } from "../api/index"

const props = defineProps<{
  role: "user" | "assistant"
  content: string
  opencodeEvents?: OpenCodeStreamEvent[]
  resultUrl?: string | null
  resultStatus?: string | null
  resultError?: string | null
}>()

const codeStreamRef = ref<HTMLElement | null>(null)
const copyButtonText = ref("复制链接")

const isOpenCodeTranscript = computed(() => props.role === "assistant" && Boolean(props.opencodeEvents?.length))

const sessionEvent = computed(() => props.opencodeEvents?.find((event) => event.kind === "session"))

const opencodeMeta = computed(() => {
  const session = sessionEvent.value
  if (!session) return "智能体会话"
  const model = [session.providerID, session.modelID].filter(Boolean).join("/")
  const sessionID = typeof session.sessionID === "string" ? session.sessionID.slice(0, 8) : ""
  return [model, sessionID ? `session ${sessionID}` : ""].filter(Boolean).join(" · ")
})

const assistantText = computed(() => {
  return (props.opencodeEvents || [])
    .filter((event) => event.kind === "assistant_delta")
    .map((event) => typeof event.content === "string" ? event.content : "")
    .join("")
    .trim()
})

interface AgentTimelineItem {
  id: string
  title: string
  detail: string
  status: string
}

interface AgentTodoItem {
  content: string
  status: string
  priority?: string
}

const runState = computed(() => {
  const statusEvent = [...(props.opencodeEvents || [])].reverse().find((event) => event.kind === "status")
  const status = statusLabel(statusEvent?.status)
  if (props.resultStatus === "active") return "完成"
  if (status === "idle") return "等待发布"
  if (status === "busy") return "运行中"
  if (status === "timeout") return "保存中"
  return "启动中"
})

const sourceModeLabel = computed(() => {
  const publish = [...(props.opencodeEvents || [])].reverse().find((event) => event.kind === "publish")
  if (publish && typeof publish.previewUrl === "string" && publish.previewUrl) return "已发布预览"
  if (props.resultStatus === "active") return "源码已保存"
  return "生成 React 源码"
})

const todoItems = computed<AgentTodoItem[]>(() => {
  const todoEvent = [...(props.opencodeEvents || [])].reverse().find((event) => event.kind === "todo")
  if (!todoEvent || !Array.isArray(todoEvent.todos)) return []
  return todoEvent.todos
    .filter((todo): todo is AgentTodoItem => Boolean(todo && typeof todo === "object" && "content" in todo))
    .map((todo) => ({
      content: String(todo.content || ""),
      status: String(todo.status || "pending"),
      priority: typeof todo.priority === "string" ? todo.priority : undefined,
    }))
})

const timelineItems = computed<AgentTimelineItem[]>(() => {
  const items: AgentTimelineItem[] = []
  const toolByCall = new Map<string, AgentTimelineItem>()

  for (const event of props.opencodeEvents || []) {
    if (event.kind === "tool") {
      const callID = typeof event.callID === "string" ? event.callID : `tool-${items.length}`
      const item = toolByCall.get(callID) || {
        id: callID,
        title: toolLabel(event),
        detail: toolDetail(event),
        status: String(event.status || "pending"),
      }
      item.title = toolLabel(event)
      item.detail = toolDetail(event)
      item.status = String(event.status || item.status)
      if (!toolByCall.has(callID)) {
        toolByCall.set(callID, item)
        items.push(item)
      }
    }
    if (event.kind === "file") {
      items.push({
        id: `file-${items.length}-${event.file || ""}`,
        title: "写入文件",
        detail: typeof event.file === "string" ? event.file : "",
        status: "completed",
      })
    }
    if (event.kind === "patch") {
      items.push({
        id: `patch-${items.length}`,
        title: "应用代码补丁",
        detail: Array.isArray(event.files) ? event.files.join(", ") : "",
        status: "completed",
      })
    }
    if (event.kind === "publish") {
      items.push({
        id: "publish",
        title: "发布预览",
        detail: typeof event.message === "string" ? event.message : "",
        status: "completed",
      })
    }
    if (event.kind === "error") {
      items.push({
        id: `error-${items.length}`,
        title: "执行出错",
        detail: typeof event.message === "string" ? event.message : "",
        status: "error",
      })
    }
  }

  return items.slice(-12)
})

function toolLabel(event: OpenCodeStreamEvent): string {
  const tool = String(event.tool || "")
  if (tool === "write") return "写入代码"
  if (tool === "edit") return "修改代码"
  if (tool === "patch") return "应用补丁"
  if (tool === "read") return "读取文件"
  if (tool === "list" || tool === "glob") return "查看文件"
  if (tool === "grep") return "搜索代码"
  if (tool === "todowrite") return "更新计划"
  return typeof event.title === "string" ? event.title : "执行工具"
}

function toolDetail(event: OpenCodeStreamEvent): string {
  const input = event.input
  if (input && typeof input === "object" && "filePath" in input && typeof input.filePath === "string") {
    return input.filePath
  }
  if (typeof event.title === "string") return event.title
  return ""
}

function statusLabel(status: unknown): string {
  if (status && typeof status === "object" && "type" in status) {
    return String((status as { type?: unknown }).type || "")
  }
  return typeof status === "string" ? status : ""
}

const isCodeStream = computed(() => (
  props.role === "assistant"
  && props.resultStatus !== "active"
  && (
    props.content.includes("```html")
    || props.content.includes("```json")
    || props.content.includes('"files"')
    || props.content.includes('"changes"')
  )
))

watch(
  () => props.content,
  async () => {
    if (!isCodeStream.value) return
    await nextTick()
    const el = codeStreamRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

const resultTitle = computed(() => {
  if (props.resultStatus === "active") return props.resultUrl ? "应用已生成" : "源码已保存"
  if (props.resultStatus === "busy") return "生成任务较多"
  if (props.resultStatus === "failed") return "应用生成失败"
  if (props.resultStatus === "edit_failed") return "应用修改失败"
  return "应用生成中"
})

const resultDescription = computed(() => {
  if (props.resultStatus === "active" && props.resultUrl) return "生成结果已自动收起，可以在右侧预览，也可以打开链接使用。"
  if (props.resultStatus === "active") return "OpenCode 已生成 React 前端源码，本轮未执行构建；可继续描述需求让智能体修改。"
  if (props.resultStatus === "busy") return "当前同时生成的任务较多，请稍后重新发送需求。"
  if (props.resultStatus === "failed") return "请调整需求后重新发送，快搭会继续尝试生成。"
  if (props.resultStatus === "edit_failed") return "已保留上一个可用版本，请调整需求后重新发送。"
  return "模型回复会保留在上方，生成完成后这里会自动收起。"
})

async function copyResultUrl() {
  if (!props.resultUrl) return
  const fullUrl = new URL(props.resultUrl, window.location.origin).toString()
  await navigator.clipboard.writeText(fullUrl)
  copyButtonText.value = "已复制"
  window.setTimeout(() => {
    copyButtonText.value = "复制链接"
  }, 1600)
}
</script>

<style scoped>
.bubble-row {
  display: flex;
  flex-direction: column;
}

.bubble-row--user {
  align-items: flex-end;
}

.bubble-row--assistant {
  align-items: flex-start;
}

.bubble {
  max-width: min(760px, 82%);
  padding: 13px 16px;
  border-radius: 20px;
  font-size: 14px;
  line-height: 1.65;
  word-break: break-word;
}

.bubble--user {
  background: linear-gradient(135deg, #475569, #6366f1);
  color: #ffffff;
  border-bottom-right-radius: 7px;
  box-shadow: 0 16px 36px rgba(79, 70, 229, 0.2);
}

.bubble--assistant {
  background: rgba(255, 255, 255, 0.86);
  color: #0f172a;
  border: 1px solid rgba(226, 232, 240, 0.8);
  border-bottom-left-radius: 7px;
  box-shadow: 0 14px 38px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(16px);
}

.bubble__placeholder {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: #64748b;
  font-weight: 650;
}

.bubble__dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #22d3ee;
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.72);
  animation: bubble-pulse 1.2s ease-in-out infinite;
}

@keyframes bubble-pulse {
  0%, 100% { transform: scale(0.8); opacity: 0.62; }
  50% { transform: scale(1); opacity: 1; }
}

.bubble__content {
  white-space: pre-wrap;
}

.opencode-chat {
  width: min(820px, 100%);
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.92)),
    radial-gradient(circle at 12% 0%, rgba(14, 165, 233, 0.1), transparent 30%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.opencode-chat__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 13px 14px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.78);
  color: #0f172a;
  font-size: 13px;
  font-weight: 760;
}

.opencode-chat__identity {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.opencode-chat__identity div {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 1px;
}

.opencode-chat__identity span {
  color: #64748b;
  font-size: 11px;
  font-weight: 650;
}

.opencode-chat__mark {
  flex: 0 0 auto;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, #0ea5e9, #10b981);
  box-shadow: 0 0 0 6px rgba(14, 165, 233, 0.1), 0 0 22px rgba(14, 165, 233, 0.32);
  animation: bubble-pulse 1.2s ease-in-out infinite;
}

.opencode-chat__badges {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.opencode-chat__badge,
.opencode-chat__state {
  border: 1px solid rgba(14, 165, 233, 0.22);
  border-radius: 999px;
  padding: 4px 8px;
  background: rgba(240, 249, 255, 0.72);
  color: #0369a1;
  font-size: 11px;
  font-weight: 760;
  white-space: nowrap;
}

.opencode-chat__badge {
  border-color: rgba(16, 185, 129, 0.22);
  background: rgba(236, 253, 245, 0.82);
  color: #047857;
}

.opencode-chat__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(240px, 0.52fr);
  min-height: 220px;
}

.opencode-chat__assistant-pane,
.opencode-chat__run-pane {
  min-width: 0;
  padding: 14px;
  display: grid;
  align-content: start;
  gap: 12px;
}

.opencode-chat__run-pane {
  border-left: 1px solid rgba(226, 232, 240, 0.78);
  background: rgba(248, 250, 252, 0.72);
}

.opencode-chat__pane-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.opencode-chat__pane-head span {
  color: #0f172a;
  font-size: 12px;
  font-weight: 820;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.opencode-chat__pane-head small {
  color: #94a3b8;
  font-size: 11px;
  font-weight: 680;
}

.opencode-chat__section-title {
  color: #64748b;
  font-size: 11px;
  font-weight: 820;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.opencode-chat__assistant {
  min-height: 118px;
  padding: 12px 13px;
  border: 1px solid rgba(203, 213, 225, 0.72);
  border-radius: 13px;
  background: #ffffff;
  color: #0f172a;
  white-space: pre-wrap;
  line-height: 1.62;
}

.opencode-chat__assistant--muted {
  color: #64748b;
}

.opencode-chat__section {
  display: grid;
  gap: 8px;
}

.opencode-chat__todo-list {
  display: grid;
  gap: 7px;
}

.opencode-chat__todo-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
}

.opencode-chat__todo-item p {
  margin: 0;
}

.opencode-chat__todo-item span {
  margin-top: 5px;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  border: 1px solid #94a3b8;
}

.opencode-chat__todo-item--in_progress span {
  border-color: #0ea5e9;
  background: #0ea5e9;
  box-shadow: 0 0 0 5px rgba(14, 165, 233, 0.11);
}

.opencode-chat__todo-item--completed span {
  border-color: #10b981;
  background: #10b981;
}

.opencode-chat__timeline {
  display: grid;
  gap: 7px;
}

.opencode-chat__event {
  position: relative;
  min-height: 32px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  padding: 8px 9px;
  border: 1px solid rgba(226, 232, 240, 0.82);
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.78);
}

.opencode-chat__event-dot {
  margin-top: 7px;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #94a3b8;
}

.opencode-chat__event--running .opencode-chat__event-dot,
.opencode-chat__event--pending .opencode-chat__event-dot {
  background: #0ea5e9;
}

.opencode-chat__event--completed .opencode-chat__event-dot {
  background: #10b981;
}

.opencode-chat__event--error .opencode-chat__event-dot {
  background: #ef4444;
}

.opencode-chat__event strong {
  display: block;
  color: #334155;
  font-size: 12px;
  font-weight: 760;
  line-height: 1.35;
}

.opencode-chat__event code {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: #64748b;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.opencode-chat__empty-run {
  border: 1px dashed rgba(148, 163, 184, 0.45);
  border-radius: 12px;
  padding: 12px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
  background: rgba(255, 255, 255, 0.58);
}

.bubble__code-shell {
  width: min(620px, 100%);
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 15px;
  background: #0f172a;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.bubble__code-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  color: #cbd5e1;
  font-size: 12px;
  font-weight: 720;
}

.bubble__code-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #22d3ee;
  box-shadow: 0 0 16px rgba(34, 211, 238, 0.7);
}

.bubble__code-stream {
  max-height: 220px;
  margin: 0;
  overflow: auto;
  padding: 12px;
  color: #dbeafe;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.bubble__code-stream::-webkit-scrollbar {
  width: 6px;
}

.bubble__code-stream::-webkit-scrollbar-track {
  background: rgba(15, 23, 42, 0.4);
}

.bubble__code-stream::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.42);
  border-radius: 999px;
}

.result-panel {
  margin-top: 10px;
  width: min(520px, 78%);
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.07);
  overflow: hidden;
  backdrop-filter: blur(14px);
}

.result-panel__summary {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 13px;
  cursor: pointer;
  list-style: none;
  color: #334155;
  font-size: 13px;
  font-weight: 720;
}

.result-panel__summary::-webkit-details-marker {
  display: none;
}

.result-panel__status {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: #22d3ee;
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.48);
}

.result-panel__status--active {
  background: #10b981;
  box-shadow: 0 0 18px rgba(16, 185, 129, 0.45);
}

.result-panel__status--failed,
.result-panel__status--edit_failed {
  background: #ef4444;
  box-shadow: 0 0 18px rgba(239, 68, 68, 0.35);
}

.result-panel__title {
  flex: 1;
}

.result-panel__toggle {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 650;
}

.result-panel__body {
  padding: 0 13px 13px;
  border-top: 1px solid rgba(226, 232, 240, 0.72);
}

.result-panel__body p {
  margin: 10px 0 12px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.65;
}

.result-panel__body .result-panel__error {
  color: #b45309;
  font-weight: 650;
}

.result-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.result-panel__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(14, 165, 233, 0.24);
  border-radius: 999px;
  padding: 8px 12px;
  background: rgba(240, 249, 255, 0.82);
  color: #0369a1;
  text-decoration: none;
  font-family: inherit;
  font-size: 12px;
  font-weight: 720;
  cursor: pointer;
  transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
}

.result-panel__btn--primary {
  border-color: rgba(16, 185, 129, 0.28);
  background: linear-gradient(135deg, #10b981, #06b6d4);
  color: #ffffff;
}

.result-panel__btn:hover {
  transform: translateY(-1px);
  border-color: rgba(14, 165, 233, 0.42);
  box-shadow: 0 10px 22px rgba(14, 165, 233, 0.14);
}

@media (max-width: 768px) {
  .bubble {
    max-width: 92%;
    padding: 12px 14px;
    font-size: 13px;
  }

  .bubble--opencode {
    width: 96%;
    max-width: 96%;
    padding: 8px;
  }

  .opencode-chat__topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .opencode-chat__badges {
    flex-wrap: wrap;
  }

  .opencode-chat__grid {
    grid-template-columns: 1fr;
  }

  .opencode-chat__run-pane {
    border-left: none;
    border-top: 1px solid rgba(226, 232, 240, 0.78);
  }

  .bubble__code-shell {
    width: min(100%, calc(100vw - 48px));
  }

  .bubble__code-stream {
    max-height: 180px;
    font-size: 11px;
  }

  .result-panel {
    width: 92%;
  }

  .result-panel__actions {
    flex-direction: column;
  }

  .result-panel__btn {
    width: 100%;
  }
}
</style>
