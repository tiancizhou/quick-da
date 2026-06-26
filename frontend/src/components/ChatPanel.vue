<template>
  <div class="chat-panel">
    <div v-if="currentAppId === null && messages.length === 0" class="home-hero" :style="heroStyle">
      <div class="home-hero__orb home-hero__orb--blue" />
      <div class="home-hero__orb home-hero__orb--orange" />

      <div class="home-hero__content">
        <div class="home-hero__badge">快搭 QD · 轻量好玩的 AI 小应用</div>
        <h1 class="home-hero__title">一个点子，马上搭成有趣小页面</h1>
        <p class="home-hero__subtitle">不用写代码，把脑洞、邀请、投票、清单或小游戏，快速变成可预览、可分享的互动小应用。</p>

        <div
          class="home-hero__composer"
          @pointermove="onHeroPointerMove"
          @pointerleave="resetHeroPointer"
        >
          <div class="home-hero__spotlight" />
          <textarea
            ref="inputRef"
            v-model="inputText"
            class="home-hero__textarea"
            placeholder="例如：帮我做一个周末旅行投票页，可以选目的地、日期和同行人数"
            rows="4"
            @keydown.enter.exact.prevent="sendMessage"
            @input="autoResize"
          />
          <div class="home-hero__composer-footer">
            <div class="home-hero__tools">
              <div class="home-hero__device-toggle" role="group" aria-label="设备偏好">
                <button
                  v-for="option in deviceOptions"
                  :key="option.value"
                  class="home-hero__device-option"
                  :class="{ 'home-hero__device-option--active': devicePreference === option.value }"
                  type="button"
                  :title="option.hint"
                  @click="devicePreference = option.value"
                >{{ option.label }}</button>
              </div>
              <div class="home-hero__style-switcher">
                <button
                  class="home-hero__style-pill"
                  :class="{ 'home-hero__style-pill--active': selectedStyleId !== null }"
                  type="button"
                  :title="'风格：' + currentStyleName"
                  @click.stop="isStylePickerOpen = !isStylePickerOpen"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/>
                    <circle cx="8" cy="10" r="1.5" fill="currentColor" stroke="none"/>
                    <circle cx="16" cy="10" r="1.5" fill="currentColor" stroke="none"/>
                    <circle cx="12" cy="15" r="1.5" fill="currentColor" stroke="none"/>
                  </svg>
                  <span class="home-hero__style-pill-text">风格：{{ selectedStyleId ? currentStyleName : "选一个视觉风格" }}</span>
                </button>
                <Transition name="popover">
                  <div v-if="isStylePickerOpen" class="home-hero__style-popover" @click.stop>
                    <div class="chat-panel__style-popover-header">选择参考风格</div>
                    <div class="chat-panel__style-grid">
                      <button
                        class="chat-panel__style-card"
                        :class="{ 'chat-panel__style-card--selected': selectedStyleId === null }"
                        type="button"
                        @click="toggleHomeStyle(null)"
                      >
                        <div class="chat-panel__style-thumb chat-panel__style-thumb--none">
                          <span>默认</span>
                        </div>
                        <span class="chat-panel__style-label">无风格</span>
                      </button>
                      <button
                        v-for="(style, index) in styles"
                        :key="style.id"
                        class="chat-panel__style-card"
                        :class="{ 'chat-panel__style-card--selected': selectedStyleId === style.id }"
                        type="button"
                        @click="toggleHomeStyle(style.id)"
                      >
                        <div class="chat-panel__style-thumb" :class="`chat-panel__style-thumb--${index % 6}`">
                          <span>{{ style.name.slice(0, 2) }}</span>
                        </div>
                        <span class="chat-panel__style-label">{{ style.name }}</span>
                      </button>
                    </div>
                  </div>
                </Transition>
              </div>
            </div>
            <button
              class="home-hero__send-btn"
              :disabled="!inputText.trim()"
              @click="sendMessage"
            >
              开始生成
            </button>
          </div>
        </div>

        <div class="home-hero__tips">
          <button v-for="tip in promptTips" :key="tip" class="home-hero__tip" @click="usePromptTip(tip)">{{ tip }}</button>
        </div>
      </div>
    </div>

    <div
      v-else
      class="chat-panel__workspace"
      :class="{
        'chat-panel__workspace--collapsed': isChatCollapsed,
        'chat-panel__workspace--mobile-chat': mobileView === 'chat',
        'chat-panel__workspace--mobile-preview': mobileView === 'preview',
      }"
    >
      <section v-if="!isChatCollapsed" class="chat-panel__conversation chat-panel__mobile-chat">
        <button class="chat-panel__collapse-btn" type="button" @click="isChatCollapsed = true">
          收起聊天
        </button>
        <div ref="messagesContainer" class="chat-panel__messages">
          <div class="chat-panel__aurora" />
          <div class="chat-panel__message-stream">
            <div v-if="messages.length === 0" class="chat-panel__empty-chat">
              <span>{{ emptyChatHint }}</span>
            </div>
            <MessageBubble
              v-for="(msg, i) in messages"
              :key="i"
              :role="msg.role"
              :content="msg.content"
              :opencode-events="msg.opencodeEvents"
              :result-url="msg.resultUrl"
              :result-status="msg.resultStatus"
              :result-error="msg.resultError"
            />
          </div>
        </div>

        <div v-if="styleNotice" class="chat-panel__style-notice">{{ styleNotice }}</div>
        <div v-if="streamProgress" class="chat-panel__progress-bar">
          <span class="chat-panel__progress-dot" />
          {{ streamProgress }}
        </div>
        <div class="chat-panel__input-bar">
          <div class="chat-panel__input-box">
            <textarea
              ref="inputRef"
              v-model="inputText"
              class="chat-panel__textarea"
              :disabled="currentAppIsStreaming"
              :placeholder="inputPlaceholder"
              rows="1"
              @keydown.enter.exact.prevent="sendMessage"
              @input="autoResize"
            />
            <div class="chat-panel__toolbar">
              <div class="chat-panel__style-switcher">
                <button
                  class="chat-panel__style-pill"
                  :class="{ 'chat-panel__style-pill--active': selectedStyleId !== null }"
                  type="button"
                  :title="'风格：' + currentStyleName"
                  @click="isStylePickerOpen = !isStylePickerOpen"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/>
                    <circle cx="8" cy="10" r="1.5" fill="currentColor" stroke="none"/>
                    <circle cx="16" cy="10" r="1.5" fill="currentColor" stroke="none"/>
                    <circle cx="12" cy="15" r="1.5" fill="currentColor" stroke="none"/>
                  </svg>
                  <span>{{ selectedStyleId ? currentStyleName : "选风格" }}</span>
                </button>
                <Transition name="popover">
                  <div v-if="isStylePickerOpen" class="chat-panel__style-popover" @click.stop>
                    <div class="chat-panel__style-popover-header">选择参考风格</div>
                    <div class="chat-panel__style-grid">
                      <button
                        class="chat-panel__style-card"
                        :class="{ 'chat-panel__style-card--selected': selectedStyleId === null }"
                        type="button"
                        @click="selectChatStyle(null)"
                      >
                        <div class="chat-panel__style-thumb chat-panel__style-thumb--none">
                          <span>默认</span>
                        </div>
                        <span class="chat-panel__style-label">无风格</span>
                      </button>
                      <button
                        v-for="(style, index) in styles"
                        :key="style.id"
                        class="chat-panel__style-card"
                        :class="{ 'chat-panel__style-card--selected': selectedStyleId === style.id }"
                        type="button"
                        @click="selectChatStyle(style.id)"
                      >
                        <div class="chat-panel__style-thumb" :class="`chat-panel__style-thumb--${index % 6}`">
                          <span>{{ style.name.slice(0, 2) }}</span>
                        </div>
                        <span class="chat-panel__style-label">{{ style.name }}</span>
                      </button>
                    </div>
                  </div>
                </Transition>
              </div>
              <div class="chat-panel__device-toggle" role="group" :aria-label="'设备偏好：' + currentDeviceOption.label">
                <button
                  v-for="option in deviceOptions"
                  :key="option.value"
                  class="chat-panel__device-option"
                  :class="{ 'chat-panel__device-option--active': devicePreference === option.value }"
                  type="button"
                  :title="option.hint"
                  @click="devicePreference = option.value"
                >{{ option.shortLabel }}</button>
              </div>
              <span class="chat-panel__toolbar-divider" />
              <button
                class="chat-panel__send-btn"
                :disabled="currentAppIsStreaming || !inputText.trim()"
                @click="sendMessage"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </section>

      <aside v-if="currentAppId" class="chat-panel__preview chat-panel__mobile-preview">
        <button
          v-if="isChatCollapsed"
          class="chat-panel__expand-btn"
          type="button"
          @click="isChatCollapsed = false"
        >
          展开聊天
        </button>
        <div class="preview-card">
          <div class="preview-card__header">
            <div>
              <span class="preview-card__eyebrow">实时预览</span>
              <h2>{{ currentApp?.name || "未命名应用" }}</h2>
              <p v-if="previewGuidance" class="preview-card__guidance">{{ previewGuidance }}</p>
            </div>
            <a
              v-if="previewUrl"
              class="preview-card__open"
              :href="previewUrl"
              target="_blank"
              rel="noopener noreferrer"
            >
              新窗口打开
            </a>
          </div>

          <div class="preview-card__body">
            <iframe
              v-if="previewUrl"
              class="preview-card__iframe"
              :src="previewUrl"
              sandbox="allow-scripts allow-forms allow-popups"
              title="应用预览"
            />
            <div v-else class="preview-card__placeholder" :class="`preview-card__placeholder--${currentApp?.status || 'creating'}`">
              <span class="preview-card__pulse" />
              <strong>{{ previewTitle }}</strong>
              <p>{{ previewDescription }}</p>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onUnmounted } from "vue"
import MessageBubble from "./MessageBubble.vue"
import { createApp, getApp, getAppPreview, listConversations, listOpenCodeEvents, sendChat, setAppStyle, type App, type DevicePreference, type OpenCodeStreamEvent, type Style } from "../api/index"

const props = withDefaults(defineProps<{
  selectedAppId: string | null
  styles: Style[]
  mobileView?: "apps" | "chat" | "preview"
}>(), {
  mobileView: "chat",
})

const emit = defineEmits<{
  "app-created": [app: App]
  "app-updated": [app: App]
}>()

interface Message {
  role: "user" | "assistant"
  content: string
  opencodeEvents?: OpenCodeStreamEvent[]
  resultUrl?: string | null
  resultStatus?: string | null
  resultError?: string | null
}

interface ResumeStreamState {
  appId: string
  messageIndex: number
}

const messages = ref<Message[]>([])
const messageCache = ref<Record<string, Message[]>>({})
const inputText = ref("")
const selectedStyleId = ref<string | null>(null)
const devicePreference = ref<DevicePreference>("mobile")
const isStylePickerOpen = ref(false)
const styleNotice = ref("")
const streamingAppIds = ref<Set<string>>(new Set())
const streamProgressByAppId = ref<Record<string, string>>({})
const isChatCollapsed = ref(false)
const currentAppId = ref<string | null>(null)
const currentApp = ref<App | null>(null)
const currentPreviewBaseUrl = ref<string | null>(null)
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const pointerX = ref(50)
const pointerY = ref(50)
const pointerTiltX = ref(0)
const pointerTiltY = ref(0)
const statusPollers: Record<string, number | undefined> = {}
const resumeStreams: Record<string, ResumeStreamState | undefined> = {}

const promptTips = [
  "生日邀请页",
  "周末投票页",
  "旅行愿望清单",
  "盲盒抽签器",
  "宠物档案卡",
  "小游戏计分板",
]

const deviceOptions: Array<{ value: DevicePreference; label: string; shortLabel: string; hint: string }> = [
  { value: "mobile", label: "手机端", shortLabel: "手机", hint: "适合分享和触屏使用" },
  { value: "desktop", label: "电脑端", shortLabel: "电脑", hint: "适合宽屏和复杂信息" },
  { value: "responsive", label: "自适应", shortLabel: "自适应", hint: "同时兼顾手机和电脑" },
]

const heroStyle = computed(() => ({
  "--pointer-x": `${pointerX.value}%`,
  "--pointer-y": `${pointerY.value}%`,
  "--tilt-x": `${pointerTiltX.value}deg`,
  "--tilt-y": `${pointerTiltY.value}deg`,
  "--shift-x": `${(pointerX.value - 50) / 7}px`,
  "--shift-y": `${(pointerY.value - 50) / 7}px`,
}))

const previewUrl = computed(() => {
  if (!currentAppId.value || !currentApp.value) return null
  if (currentApp.value.status === "active" || (currentApp.value.status === "editing" && currentApp.value.version > 0) || currentApp.value.status === "edit_failed") {
    return currentPreviewBaseUrl.value ? cacheBustPreviewUrl(currentPreviewBaseUrl.value, currentApp.value.version) : null
  }
  return null
})

const emptyChatHint = computed(() => {
  if (currentApp.value?.status === "active") return "继续描述要调整的地方，快搭会在当前应用上修改。"
  if (currentApp.value?.status === "edit_failed") return "上一次修改失败，旧版本已保留；可以继续描述要调整的地方。"
  if (currentApp.value?.status === "failed") return "上一次生成失败，可以调整需求后重新发送。"
  return "继续描述你的应用需求，右侧会显示生成后的页面预览。"
})

const inputPlaceholder = computed(() => {
  if (currentAppIsStreaming.value) return currentApp.value?.version ? "正在修改中…" : "正在生成中…"
  if (currentApp.value?.status === "active") return "继续描述要调整的内容…"
  if (currentApp.value?.status === "edit_failed") return "旧版本已保留，继续描述要怎么修改…"
  if (currentApp.value?.status === "failed") return "调整需求后重新发送…"
  return "描述你想要的应用功能…"
})

const previewGuidance = computed(() => {
  if (!previewUrl.value) return ""
  if (currentApp.value?.status === "editing" || (currentAppIsStreaming.value && currentApp.value?.version)) return "正在修改中，当前预览仍是上一个可用版本。"
  if (currentApp.value?.status === "edit_failed") return "修改失败但旧版本已保留，可在左侧继续描述调整。"
  return "想继续调整？直接在左侧描述要修改的地方。"
})

const previewTitle = computed(() => {
  if (currentApp.value?.status === "failed") return "应用生成失败"
  if (currentApp.value?.status === "editing" && previewUrl.value) return "正在修改应用"
  if (currentApp.value?.status === "edit_failed") return "应用修改失败"
  if (currentAppIsStreaming.value || currentApp.value?.status === "creating" || currentApp.value?.status === "editing") return "正在准备预览"
  return "预览暂不可用"
})

const previewDescription = computed(() => {
  if (currentApp.value?.status === "failed") return "可以在左侧调整需求后重新发送，快搭会再次尝试生成。"
  if (currentApp.value?.status === "editing" && previewUrl.value) return "旧版本预览仍可使用，修改完成后这里会自动刷新。"
  if (currentApp.value?.status === "edit_failed") return "上一个可用版本已保留，可以继续描述要调整的内容。"
  if (currentAppIsStreaming.value || currentApp.value?.status === "creating" || currentApp.value?.status === "editing") return "模型回复会正常显示在左侧，页面生成完成后这里会自动切换为实时预览。"
  return "当前应用还没有可打开的页面。"
})

const currentStyleName = computed(() => props.styles.find((style) => style.id === selectedStyleId.value)?.name || "无风格")
const currentDeviceOption = computed(() => deviceOptions.find((option) => option.value === devicePreference.value) || deviceOptions[0])
const currentAppIsStreaming = computed(() => Boolean(currentAppId.value && streamingAppIds.value.has(currentAppId.value)))
const streamProgress = computed(() => currentAppId.value ? streamProgressByAppId.value[currentAppId.value] || "" : "")

// Watch for selectedAppId changes
watch(
  () => props.selectedAppId,
  async (newId) => {
    await loadSelectedApp(newId)
  },
  { immediate: true },
)

async function loadSelectedApp(newId: string | null) {
  if (newId === currentAppId.value && (newId === null || currentApp.value)) {
    return
  }

  if (currentAppId.value) {
    messageCache.value[currentAppId.value] = messages.value
  }

  if (newId === null) {
    messages.value = []
    currentAppId.value = null
    currentApp.value = null
    currentPreviewBaseUrl.value = null
    isChatCollapsed.value = false
    return
  }

  currentAppId.value = newId
  isChatCollapsed.value = false

  try {
    const [app, conversations, opencodeRecords] = await Promise.all([
      getApp(newId),
      listConversations(newId),
      listOpenCodeEvents(newId).catch(() => []),
    ])
    currentApp.value = app
    selectedStyleId.value = app.style_id || null
    await refreshPreviewBaseUrl(newId, app)

    if (app.status === "creating" || app.status === "editing") {
      setAppStreaming(newId, true)
      setAppProgress(newId, app.progress || "正在生成中...")
    }

    if (messageCache.value[newId]) {
      messages.value = messageCache.value[newId]
      if (app.status === "creating" || app.status === "editing") {
        startStatusPolling(newId)
      }
      await scrollToBottom()
      return
    }

    const loadedMessages: Message[] = conversations
      .filter((conversation) => conversation.role === "user" || conversation.role === "assistant")
      .map((conversation) => ({
        role: conversation.role as "user" | "assistant",
        content: conversation.role === "assistant" ? normalizeHistoricalAssistantContent(conversation.content) : conversation.content,
      }))
    const historicalOpenCodeEvents = opencodeRecords
      .map((record) => record.payload)
      .filter((event): event is OpenCodeStreamEvent => Boolean(event && typeof event === "object" && typeof event.kind === "string"))

    const lastAssistant = [...loadedMessages].reverse().find((message) => message.role === "assistant")
    if (lastAssistant) {
      if (historicalOpenCodeEvents.length) {
        lastAssistant.opencodeEvents = historicalOpenCodeEvents
        lastAssistant.content = ""
      }
      lastAssistant.resultStatus = app.status
      lastAssistant.resultUrl = app.status === "active" && currentPreviewBaseUrl.value ? cacheBustPreviewUrl(currentPreviewBaseUrl.value, app.version) : null
    } else if (historicalOpenCodeEvents.length) {
      loadedMessages.push({
        role: "assistant",
        content: "",
        opencodeEvents: historicalOpenCodeEvents,
        resultStatus: app.status,
        resultUrl: app.status === "active" && currentPreviewBaseUrl.value ? cacheBustPreviewUrl(currentPreviewBaseUrl.value, app.version) : null,
      })
    }
    if (app.status === "creating") {
      if (!lastAssistant) {
        loadedMessages.push({ role: "assistant", content: "" })
      }
      messageCache.value[newId] = loadedMessages
      messages.value = loadedMessages
      resumeGeneratingApp(newId)
      await scrollToBottom()
      return
    }

    messageCache.value[newId] = loadedMessages
    messages.value = loadedMessages
  } catch (err) {
    currentApp.value = null
    messages.value = [{ role: "assistant", content: "加载聊天记录失败，请稍后重试。", resultStatus: "failed" }]
  }

  await scrollToBottom()
}

async function sendMessage() {
  if (currentAppIsStreaming.value) return
  const userMessage = inputText.value.trim()
  if (!userMessage) return

  // 1. Push user message and clear input
  messages.value.push({ role: "user", content: userMessage })
  inputText.value = ""
  resetTextareaHeight()
  await scrollToBottom()

  // 2. Create app if this is a new conversation
  if (currentAppId.value === null) {
    try {
      const newApp = await createApp(selectedStyleId.value)
      currentAppId.value = newApp.id
      currentApp.value = newApp
      selectedStyleId.value = newApp.style_id || selectedStyleId.value
      isChatCollapsed.value = false
      emit("app-created", newApp)
    } catch (err) {
      messages.value.push({
        role: "assistant",
        content: "创建应用失败，请稍后重试。",
        resultStatus: "failed",
      })
      return
    }
  }

  // 3. Push streaming placeholder
  messages.value.push({ role: "assistant", content: "" })
  await scrollToBottom()

  const appId = currentAppId.value!
  const requestedDevicePreference = devicePreference.value
  setAppStreaming(appId, true)
  messageCache.value[appId] = messages.value
  startStatusPolling(appId)

  try {
    await sendChat(
      appId,
      userMessage,
      requestedDevicePreference,
      // onChunk
      async (content) => {
        const appMessages = messageCache.value[appId]
        const last = appMessages?.[appMessages.length - 1]
        if (last && last.role === "assistant") {
          last.content += content
        }
        if (currentAppId.value === appId) {
          messages.value = appMessages
          await scrollToBottom()
        }
      },
      // onProgress
      (progress) => {
        if (currentAppId.value === appId) {
          setAppProgress(appId, progress)
        }
      },
      // onOpenCode
      async (event) => {
        const appMessages = messageCache.value[appId]
        const last = appMessages?.[appMessages.length - 1]
        if (last && last.role === "assistant") {
          last.opencodeEvents = [...(last.opencodeEvents || []), event]
        }
        if (currentAppId.value === appId) {
          messages.value = appMessages
          await scrollToBottom()
        }
      },
      // onResult
      async (url, status, error) => {
        clearAppProgress(appId)
        const appMessages = messageCache.value[appId]
        const last = appMessages?.[appMessages.length - 1]
        let updatedApp = currentApp.value
        try {
          updatedApp = await getApp(appId)
        } catch {
          updatedApp = currentApp.value ? { ...currentApp.value, status: status === "active" ? "active" : "failed" } : null
        }
        if (updatedApp) {
          currentApp.value = updatedApp
          await refreshPreviewBaseUrl(appId, updatedApp, url)
          emit("app-updated", updatedApp)
        }
        if (last && last.role === "assistant") {
          last.content = status === "active" && last.opencodeEvents?.length ? last.content : (status === "active" ? normalizeSuccessfulContent(last.content) : normalizeGeneratedContent(last.content, status))
          last.resultUrl = status === "active" && previewAvailable(appId, url) ? resultPreviewUrl(appId, url, updatedApp?.version) : null
          last.resultStatus = status
          last.resultError = error
        }
        if (currentAppId.value === appId) {
          messages.value = appMessages
          scrollToBottom()
        }
        setAppStreaming(appId, false)
        stopStatusPolling(appId)
      },
    )
  } catch (err) {
    clearAppProgress(appId)
    const appMessages = messageCache.value[appId]
    const last = appMessages?.[appMessages.length - 1]
    if (last && last.role === "assistant") {
      last.content = last.content || "发生错误，请重试。"
      last.resultStatus = currentApp.value?.version ? "edit_failed" : "failed"
    }
    if (currentAppId.value === appId) {
      messages.value = appMessages
    }
    setAppStreaming(appId, false)
    stopStatusPolling(appId)
  }
}

async function resumeGeneratingApp(appId: string) {
  if (resumeStreams[appId]) return
  setAppStreaming(appId, true)
  const appMessages = messageCache.value[appId] || messages.value
  const assistantIndex = [...appMessages].reverse().findIndex((message: Message) => message.role === "assistant")
  const messageIndex = assistantIndex === -1 ? -1 : appMessages.length - 1 - assistantIndex
  resumeStreams[appId] = { appId, messageIndex }
  startStatusPolling(appId)

  try {
    await sendChat(
      appId,
      "",
      devicePreference.value,
      async (content) => {
        const currentMessages = messageCache.value[appId]
        const target = currentMessages?.[resumeStreams[appId]?.messageIndex ?? -1]
        if (target && target.role === "assistant") {
          target.content += content
        }
        if (currentAppId.value === appId) {
          messages.value = currentMessages
          await scrollToBottom()
        }
      },
      (progress) => {
        setAppProgress(appId, progress)
      },
      async (event) => {
        const currentMessages = messageCache.value[appId]
        const target = currentMessages?.[resumeStreams[appId]?.messageIndex ?? -1]
        if (target && target.role === "assistant") {
          target.opencodeEvents = [...(target.opencodeEvents || []), event]
        }
        if (currentAppId.value === appId) {
          messages.value = currentMessages
          await scrollToBottom()
        }
      },
      async (url, status, error) => {
        clearAppProgress(appId)
        const currentMessages = messageCache.value[appId]
        const target = currentMessages?.[resumeStreams[appId]?.messageIndex ?? -1]
        let updatedApp: App | null = null
        try {
          updatedApp = await getApp(appId)
          if (currentAppId.value === appId) {
            currentApp.value = updatedApp
          }
          await refreshPreviewBaseUrl(appId, updatedApp, url)
          emit("app-updated", updatedApp)
        } catch {
          if (currentAppId.value === appId) {
            currentApp.value = null
          }
        }
        if (target && target.role === "assistant") {
          target.content = status === "active" && target.opencodeEvents?.length ? target.content : (status === "active" ? normalizeSuccessfulContent(target.content) : normalizeGeneratedContent(target.content, status))
          target.resultUrl = status === "active" && previewAvailable(appId, url) ? resultPreviewUrl(appId, url, updatedApp?.version) : null
          target.resultStatus = status
          target.resultError = error
        }
        if (currentAppId.value === appId) {
          messages.value = currentMessages
          await scrollToBottom()
        }
        setAppStreaming(appId, false)
        delete resumeStreams[appId]
        stopStatusPolling(appId)
      },
    )
  } catch {
    clearAppProgress(appId)
    setAppStreaming(appId, false)
    delete resumeStreams[appId]
    stopStatusPolling(appId)
  }
}

function projectPreviewUrl(appId: string): string {
  return `/generated/${appId}/project/index.html`
}

function cacheBustPreviewUrl(url: string, version?: number | null): string {
  const separator = url.includes("?") ? "&" : "?"
  return `${url}${separator}t=${version || Date.now()}`
}

function resultPreviewUrl(appId: string, url: string | null, version?: number | null): string {
  return cacheBustPreviewUrl(url || currentPreviewBaseUrl.value || projectPreviewUrl(appId), version)
}

function previewAvailable(_appId: string, url: string | null): boolean {
  return Boolean(url || currentPreviewBaseUrl.value || false)
}

async function refreshPreviewBaseUrl(appId: string, app: App, fallbackUrl?: string | null): Promise<void> {
  if (!["active", "editing", "edit_failed"].includes(app.status) || app.version <= 0) return
  if (fallbackUrl) {
    currentPreviewBaseUrl.value = fallbackUrl
    return
  }
  try {
    const preview = await getAppPreview(appId)
    currentPreviewBaseUrl.value = preview.url
  } catch {
    currentPreviewBaseUrl.value = null
  }
}

function normalizeGeneratedContent(content: string, status: string): string {
  if (status === "active" && looksLikeGeneratedArtifact(content)) return "应用已生成或更新，可以在右侧预览。"
  if (status !== "active" && content.length > 3000 && looksLikeGeneratedArtifact(content)) return "生成失败，模型返回的项目格式无法解析。请调整需求后重试。"
  return normalizeAgentActivityContent(content)
}

function normalizeSuccessfulContent(content: string): string {
  const trimmed = normalizeAgentActivityContent(content).trim()
  if (!trimmed || looksLikeGeneratedArtifact(trimmed)) return "应用已生成或更新，可以在右侧预览。"
  if (trimmed.includes("可以在右侧预览")) return trimmed
  return `${trimmed}\n\n应用已生成或更新，可以在右侧预览。`
}

function normalizeHistoricalAssistantContent(content: string): string {
  if (looksLikeGeneratedArtifact(content)) return "应用已生成或更新，可以在右侧预览。"
  return normalizeAgentActivityContent(content)
}

function normalizeAgentActivityContent(content: string): string {
  const lines = content
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)

  if (!lines.some((line) => line.includes("OpenCode") || line.includes("opencode-workspace") || line.includes("静态前端"))) {
    return content
  }

  const cleaned = lines
    .filter((line) => !line.includes("请作为一个前端代码智能体"))
    .filter((line) => !line.includes("只允许生成浏览器"))
    .filter((line) => !line.includes("必须创建或更新"))
    .filter((line) => !line.includes("不要运行 npm"))
    .filter((line) => !line.includes("生成结果会通过"))
    .filter((line) => !line.includes("请确保移动端"))
    .filter((line) => !line.includes("设备布局目标"))
    .filter((line) => !line.includes("历史对话"))
    .filter((line) => !line.startsWith("user:"))
    .filter((line) => !line.includes("本次用户需求"))
    .map((line) => line
      .replace(/app\/data\/apps\/[0-9a-f-]+\/opencode-workspace\/?/gi, "")
      .replace(/.*opencode-workspace\/?/gi, "")
      .replace(/^已完成：\s*$/g, "完成：检查工作区")
      .replace(/^完成：\s*$/g, "完成：检查工作区")
      .replace(/^已写入：/g, "写入文件：")
      .trim())
    .filter(Boolean)

  return cleaned.length ? cleaned.join("\n") : "应用已生成或更新，可以在右侧预览。"
}

function looksLikeGeneratedArtifact(content: string): boolean {
  return content.includes("```html")
    || content.includes("```json")
    || content.includes('"files"')
    || content.includes('"changes"')
    || content.includes("<!DOCTYPE html")
    || content.includes("<html")
}

function setAppStreaming(appId: string, streaming: boolean) {
  const next = new Set(streamingAppIds.value)
  if (streaming) {
    next.add(appId)
  } else {
    next.delete(appId)
  }
  streamingAppIds.value = next
}

function setAppProgress(appId: string, progress: string) {
  streamProgressByAppId.value = {
    ...streamProgressByAppId.value,
    [appId]: progress,
  }
}

function clearAppProgress(appId: string) {
  const next = { ...streamProgressByAppId.value }
  delete next[appId]
  streamProgressByAppId.value = next
}

function stopStatusPolling(appId: string) {
  const poller = statusPollers[appId]
  if (poller !== undefined) {
    window.clearInterval(poller)
    delete statusPollers[appId]
  }
}

function startStatusPolling(appId: string) {
  stopStatusPolling(appId)
  statusPollers[appId] = window.setInterval(async () => {
    try {
      const app = await getApp(appId)
      if (currentAppId.value === appId) {
        currentApp.value = app
        await refreshPreviewBaseUrl(appId, app)
      }
      if ((app.status === "creating" || app.status === "editing") && app.progress) {
        setAppProgress(appId, app.progress)
      }
      if (app.status === "creating" || app.status === "editing") {
        return
      }

      setAppStreaming(appId, false)
      stopStatusPolling(appId)
      emit("app-updated", app)
      clearAppProgress(appId)

      let loadedMessages: Message[] = []
      try {
        const [conversations, opencodeRecords] = await Promise.all([
          listConversations(appId),
          listOpenCodeEvents(appId).catch(() => []),
        ])
        const historicalOpenCodeEvents = opencodeRecords
          .map((record) => record.payload)
          .filter((event): event is OpenCodeStreamEvent => Boolean(event && typeof event === "object" && typeof event.kind === "string"))
        loadedMessages = conversations
          .filter((conversation) => conversation.role === "user" || conversation.role === "assistant")
          .map((conversation) => ({
            role: conversation.role as "user" | "assistant",
            content: conversation.role === "assistant" ? normalizeHistoricalAssistantContent(conversation.content) : conversation.content,
          }))
        const lastAssistant = [...loadedMessages].reverse().find((message) => message.role === "assistant")
        if (lastAssistant && historicalOpenCodeEvents.length) {
          lastAssistant.opencodeEvents = historicalOpenCodeEvents
          lastAssistant.content = ""
        } else if (!lastAssistant && historicalOpenCodeEvents.length) {
          loadedMessages.push({ role: "assistant", content: "", opencodeEvents: historicalOpenCodeEvents })
        }
      } catch {
        loadedMessages = messageCache.value[appId] || messages.value
      }

      if (loadedMessages.length === 0 && app.status === "failed") {
        loadedMessages.push({ role: "assistant", content: "应用生成失败，请调整需求后重试。", resultStatus: "failed" })
      }

      const lastAssistant = [...loadedMessages].reverse().find((message) => message.role === "assistant")
      if (lastAssistant) {
        if (!lastAssistant.opencodeEvents?.length) {
          lastAssistant.content = normalizeGeneratedContent(lastAssistant.content, app.status)
            || (app.status === "active" ? "应用已生成或更新，可以在右侧预览。" : "生成失败，请重新描述需求后再试。")
        }
        lastAssistant.resultStatus = app.status
        lastAssistant.resultUrl = (app.status === "active" || app.status === "edit_failed") && currentPreviewBaseUrl.value ? cacheBustPreviewUrl(currentPreviewBaseUrl.value, app.version) : null
      } else if (app.status === "active") {
        loadedMessages.push({ role: "assistant", content: "源码已生成并保存。", resultStatus: "active", resultUrl: currentPreviewBaseUrl.value ? cacheBustPreviewUrl(currentPreviewBaseUrl.value, app.version) : null })
      }

      messageCache.value[appId] = loadedMessages
      if (currentAppId.value === appId) {
        currentApp.value = app
        messages.value = loadedMessages
        await scrollToBottom()
      }
    } catch {
      clearAppProgress(appId)
      setAppStreaming(appId, false)
      delete resumeStreams[appId]
      stopStatusPolling(appId)
    }
  }, 2000)
}

async function scrollToBottom() {
  await nextTick()
  const el = messagesContainer.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

function usePromptTip(tip: string) {
  inputText.value = `帮我做一个${tip}`
  inputRef.value?.focus()
}

function toggleHomeStyle(styleId: string | null) {
  selectedStyleId.value = selectedStyleId.value === styleId ? null : styleId
  isStylePickerOpen.value = false
}

async function selectChatStyle(styleId: string | null) {
  selectedStyleId.value = styleId
  isStylePickerOpen.value = false
  if (currentAppId.value) {
    const updatedApp = await setAppStyle(currentAppId.value, styleId)
    currentApp.value = updatedApp
  }
  styleNotice.value = "风格已切换，下次生成时生效。"
  window.setTimeout(() => {
    styleNotice.value = ""
  }, 2000)
}

function onHeroPointerMove(event: PointerEvent) {
  if (event.pointerType !== "mouse") return
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * 100
  const y = ((event.clientY - rect.top) / rect.height) * 100
  pointerX.value = Math.min(100, Math.max(0, x))
  pointerY.value = Math.min(100, Math.max(0, y))
  pointerTiltX.value = (50 - pointerY.value) / 12
  pointerTiltY.value = (pointerX.value - 50) / 12
}

function resetHeroPointer() {
  pointerX.value = 50
  pointerY.value = 50
  pointerTiltX.value = 0
  pointerTiltY.value = 0
}

function autoResize(event: Event) {
  const el = event.target as HTMLTextAreaElement
  el.style.height = "auto"
  el.style.height = Math.min(el.scrollHeight, 160) + "px"
}

function resetTextareaHeight() {
  if (inputRef.value) {
    inputRef.value.style.height = "auto"
  }
}

function onDocumentClick() {
  if (isStylePickerOpen.value) {
    isStylePickerOpen.value = false
  }
}

onMounted(() => document.addEventListener("click", onDocumentClick))
onUnmounted(() => {
  document.removeEventListener("click", onDocumentClick)
  Object.keys(statusPollers).forEach(stopStatusPolling)
})
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 18% 12%, rgba(56, 189, 248, 0.2) 0%, transparent 26%),
    radial-gradient(circle at 82% 20%, rgba(251, 146, 60, 0.2) 0%, transparent 24%),
    linear-gradient(135deg, #f8fbff 0%, #fff7ed 48%, #f0f9ff 100%);
  position: relative;
}

.home-hero {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 56px 32px;
  text-align: center;
  overflow: hidden;
}

.home-hero__content {
  position: relative;
  z-index: 1;
  width: min(820px, 100%);
}

.home-hero__orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(2px);
  opacity: 0.62;
}

.home-hero__orb--blue {
  width: 180px;
  height: 180px;
  top: 12%;
  left: 10%;
  background: radial-gradient(circle, rgba(14, 165, 233, 0.28), transparent 68%);
  transform: translate3d(calc(var(--shift-x, 0px) * -0.6), calc(var(--shift-y, 0px) * -0.6), 0);
  transition: transform 0.28s ease-out;
  will-change: transform;
}

.home-hero__orb--orange {
  width: 220px;
  height: 220px;
  right: 8%;
  bottom: 10%;
  background: radial-gradient(circle, rgba(168, 85, 247, 0.18), transparent 68%);
  transform: translate3d(calc(var(--shift-x, 0px) * 0.7), calc(var(--shift-y, 0px) * 0.7), 0);
  transition: transform 0.28s ease-out;
  will-change: transform;
}

.home-hero__badge {
  display: inline-flex;
  align-items: center;
  padding: 7px 14px;
  border: 1px solid rgba(14, 165, 233, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #0369a1;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 18px;
  box-shadow: 0 10px 28px rgba(14, 165, 233, 0.1);
}

.home-hero__title {
  margin: 0;
  font-size: clamp(32px, 5vw, 52px);
  line-height: 1.12;
  letter-spacing: -0.06em;
  color: #0f172a;
  font-weight: 820;
  transform: translate3d(calc(var(--shift-x, 0px) * 0.18), calc(var(--shift-y, 0px) * 0.18), 0);
  transition: transform 0.24s ease-out;
  will-change: transform;
}

.home-hero__subtitle {
  margin: 18px auto 30px;
  max-width: 680px;
  font-size: 16px;
  color: #64748b;
  line-height: 1.8;
}

.home-hero__composer {
  position: relative;
  width: min(760px, 100%);
  margin: 0 auto;
  background:
    radial-gradient(circle at var(--pointer-x, 50%) var(--pointer-y, 50%), rgba(34, 211, 238, 0.2), transparent 34%),
    rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(14, 165, 233, 0.24);
  border-radius: 28px;
  box-shadow:
    0 28px 80px rgba(15, 23, 42, 0.12),
    0 0 0 1px rgba(255, 255, 255, 0.62) inset;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  backdrop-filter: blur(18px);
  transform: perspective(900px) rotateX(var(--tilt-x, 0deg)) rotateY(var(--tilt-y, 0deg)) translate3d(0, 0, 0);
  transform-style: preserve-3d;
  transition: transform 0.22s ease-out, box-shadow 0.22s ease-out, border-color 0.22s ease-out;
  will-change: transform;
}

.home-hero__composer:hover {
  border-color: rgba(6, 182, 212, 0.42);
  box-shadow:
    0 32px 90px rgba(15, 23, 42, 0.14),
    0 0 42px rgba(34, 211, 238, 0.16),
    0 0 0 1px rgba(255, 255, 255, 0.72) inset;
}

.home-hero__spotlight {
  position: absolute;
  inset: 0;
  border-radius: 28px;
  pointer-events: none;
  background: radial-gradient(circle at var(--pointer-x, 50%) var(--pointer-y, 50%), rgba(129, 140, 248, 0.22), transparent 24%);
  opacity: 0;
  transition: opacity 0.2s ease-out;
  mix-blend-mode: screen;
}

.home-hero__composer:hover .home-hero__spotlight {
  opacity: 1;
}

.home-hero__textarea {
  position: relative;
  z-index: 1;
  width: 100%;
  min-height: 122px;
  resize: none;
  border: none;
  outline: none;
  font-size: 15px;
  line-height: 1.7;
  color: #0f172a;
  font-family: inherit;
  background: transparent;
}

.home-hero__textarea::placeholder {
  color: #94a3b8;
}

.home-hero__composer-footer {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.home-hero__tools {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.home-hero__device-toggle,
.chat-panel__device-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
}

.home-hero__device-option,
.chat-panel__device-option {
  border: none;
  border-radius: 999px;
  background: transparent;
  color: #64748b;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}

.home-hero__device-option {
  padding: 6px 10px;
}

.chat-panel__device-option {
  padding: 5px 8px;
}

.home-hero__device-option:hover,
.chat-panel__device-option:hover {
  color: #0284c7;
}

.home-hero__device-option--active,
.chat-panel__device-option--active {
  background: rgba(14, 165, 233, 0.12);
  color: #0284c7;
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.1);
}

.home-hero__style-switcher {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
}

.home-hero__style-pill {
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 999px;
  padding: 8px 12px;
  background: rgba(248, 250, 252, 0.82);
  color: #64748b;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font: inherit;
  font-size: 12px;
  font-weight: 720;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s, color 0.15s, background 0.15s, box-shadow 0.15s;
}

.home-hero__style-pill:hover,
.home-hero__style-pill--active {
  border-color: rgba(14, 165, 233, 0.46);
  color: #0284c7;
  background: rgba(240, 249, 255, 0.92);
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.1);
}

.home-hero__style-pill-text {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.home-hero__style-popover {
  position: absolute;
  left: 0;
  bottom: calc(100% + 12px);
  width: 340px;
  padding: 12px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16), 0 0 0 1px rgba(255,255,255,0.6) inset;
  backdrop-filter: blur(20px);
  z-index: 10;
}

.home-hero__send-btn {
  flex-shrink: 0;
  border: none;
  border-radius: 999px;
  padding: 11px 20px;
  background: linear-gradient(135deg, #0284c7, #f97316);
  color: #ffffff;
  font-size: 14px;
  font-weight: 750;
  cursor: pointer;
  box-shadow: 0 16px 34px rgba(2, 132, 199, 0.24);
  transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s;
}

.home-hero__send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 20px 40px rgba(2, 132, 199, 0.3);
}

.home-hero__send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

.home-hero__tips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 24px;
}

.home-hero__tip {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 999px;
  padding: 9px 15px;
  background: rgba(255, 255, 255, 0.76);
  color: #475569;
  font-size: 13px;
  font-weight: 620;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
  transition: transform 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s;
}

.home-hero__tip:hover {
  border-color: rgba(14, 165, 233, 0.42);
  color: #0369a1;
  box-shadow: 0 14px 30px rgba(14, 165, 233, 0.12);
  transform: translateY(-1px);
}

/* Messages */
.chat-panel__workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(430px, 0.92fr) minmax(460px, 1.08fr);
  gap: 18px;
  padding: 18px;
  box-sizing: border-box;
  overflow: hidden;
}

.chat-panel__workspace--collapsed {
  grid-template-columns: minmax(0, 1fr);
}

.chat-panel__collapse-btn,
.chat-panel__expand-btn {
  position: absolute;
  z-index: 3;
  border: 1px solid rgba(14, 165, 233, 0.22);
  border-radius: 999px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.88);
  color: #0369a1;
  font: inherit;
  font-size: 12px;
  font-weight: 740;
  cursor: pointer;
  box-shadow: 0 12px 28px rgba(14, 165, 233, 0.12);
  backdrop-filter: blur(14px);
  transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
}

.chat-panel__collapse-btn:hover,
.chat-panel__expand-btn:hover {
  transform: translateY(-1px);
  border-color: rgba(14, 165, 233, 0.42);
  box-shadow: 0 16px 34px rgba(14, 165, 233, 0.18);
}

.chat-panel__collapse-btn {
  top: 14px;
  right: 14px;
}

.chat-panel__expand-btn {
  top: 14px;
  left: 14px;
}

.chat-panel__conversation {
  position: relative;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(226, 232, 240, 0.82);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.66);
  box-shadow: 0 22px 70px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(18px);
}

.chat-panel__messages {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
}

.chat-panel__aurora {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 18% 18%, rgba(34, 211, 238, 0.16), transparent 30%),
    radial-gradient(circle at 82% 8%, rgba(251, 146, 60, 0.1), transparent 28%),
    radial-gradient(circle at 50% 76%, rgba(129, 140, 248, 0.1), transparent 34%);
}

.chat-panel__message-stream {
  position: relative;
  z-index: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.chat-panel__empty-chat {
  align-self: center;
  margin-top: 18px;
  padding: 12px 15px;
  border: 1px dashed rgba(14, 165, 233, 0.28);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.72);
  color: #64748b;
  font-size: 13px;
}

.chat-panel__preview {
  position: relative;
  min-width: 0;
  min-height: 0;
  display: flex;
}

.preview-card {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(14, 165, 233, 0.18);
  border-radius: 28px;
  background:
    radial-gradient(circle at 12% 10%, rgba(34, 211, 238, 0.13), transparent 28%),
    rgba(255, 255, 255, 0.82);
  box-shadow: 0 26px 80px rgba(15, 23, 42, 0.1);
  backdrop-filter: blur(18px);
}

.preview-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 17px 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.78);
}

.preview-card__eyebrow {
  display: block;
  margin-bottom: 4px;
  color: #0284c7;
  font-size: 11px;
  font-weight: 820;
  letter-spacing: 0.14em;
}

.preview-card__header h2 {
  margin: 0;
  color: #0f172a;
  font-size: 18px;
  letter-spacing: -0.03em;
}

.preview-card__guidance {
  margin: 6px 0 0;
  max-width: 360px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.preview-card__open {
  flex-shrink: 0;
  border: 1px solid rgba(14, 165, 233, 0.24);
  border-radius: 999px;
  padding: 8px 12px;
  background: rgba(240, 249, 255, 0.82);
  color: #0369a1;
  text-decoration: none;
  font-size: 12px;
  font-weight: 740;
}

.preview-card__body {
  flex: 1;
  min-height: 0;
  padding: 12px;
  background: rgba(248, 250, 252, 0.72);
}

.preview-card__iframe {
  width: 100%;
  height: 100%;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 20px;
  background: #ffffff;
  box-shadow: 0 18px 46px rgba(15, 23, 42, 0.08);
}

.preview-card__placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px dashed rgba(14, 165, 233, 0.28);
  border-radius: 20px;
  background:
    radial-gradient(circle at 50% 34%, rgba(34, 211, 238, 0.18), transparent 28%),
    rgba(255, 255, 255, 0.68);
  text-align: center;
  padding: 28px;
}

.preview-card__placeholder strong {
  color: #0f172a;
  font-size: 18px;
}

.preview-card__placeholder p {
  max-width: 360px;
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

.preview-card__placeholder--failed {
  border-color: rgba(248, 113, 113, 0.36);
  background:
    radial-gradient(circle at 50% 34%, rgba(248, 113, 113, 0.12), transparent 28%),
    rgba(255, 255, 255, 0.72);
}

.preview-card__pulse {
  width: 13px;
  height: 13px;
  border-radius: 999px;
  background: #22d3ee;
  box-shadow: 0 0 0 9px rgba(34, 211, 238, 0.12), 0 0 26px rgba(34, 211, 238, 0.5);
  animation: preview-pulse 1.4s ease-in-out infinite;
}

@keyframes preview-pulse {
  0%, 100% { transform: scale(0.88); opacity: 0.72; }
  50% { transform: scale(1); opacity: 1; }
}

.chat-panel__messages::-webkit-scrollbar {
  width: 6px;
}

.chat-panel__messages::-webkit-scrollbar-track {
  background: transparent;
}

.chat-panel__messages::-webkit-scrollbar-thumb {
  background: rgba(15, 23, 42, 0.16);
  border-radius: 4px;
}

.chat-panel__style-notice {
  margin: 0 14px 10px;
  padding: 9px 12px;
  border: 1px solid rgba(14, 165, 233, 0.18);
  border-radius: 14px;
  background: rgba(240, 249, 255, 0.86);
  color: #0369a1;
  font-size: 12px;
  font-weight: 680;
}

.chat-panel__progress-bar {
  margin: 0 14px 10px;
  padding: 9px 12px;
  border: 1px solid rgba(226, 232, 240, 0.8);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.86);
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-panel__progress-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #22d3ee;
  flex-shrink: 0;
  animation: progress-pulse 1.2s ease-in-out infinite;
}

@keyframes progress-pulse {
  0%, 100% { opacity: 0.5; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
}

/* Input bar */
.chat-panel__input-bar {
  padding: 12px 14px 14px;
  background: rgba(255, 255, 255, 0.82);
  border-top: 1px solid rgba(226, 232, 240, 0.82);
  box-shadow: 0 -12px 34px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(18px);
}

.chat-panel__input-box {
  display: flex;
  flex-direction: column;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.9);
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
  overflow: hidden;
}

.chat-panel__input-box:focus-within {
  border-color: rgba(14, 165, 233, 0.62);
  background: #ffffff;
  box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.1);
}

.chat-panel__textarea {
  width: 100%;
  resize: none;
  border: none;
  outline: none;
  padding: 12px 14px 6px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  background: transparent;
  color: #0f172a;
  overflow-y: auto;
  max-height: 160px;
}

.chat-panel__textarea:disabled {
  color: #94a3b8;
  cursor: not-allowed;
}

.chat-panel__textarea::placeholder {
  color: #94a3b8;
}

.chat-panel__toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
}

.chat-panel__toolbar-divider {
  flex: 1;
}

/* Style switcher */
.chat-panel__style-switcher {
  position: relative;
}

.chat-panel__style-pill {
  max-width: 128px;
  min-height: 32px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 999px;
  padding: 6px 10px;
  background: rgba(248, 250, 252, 0.9);
  color: #64748b;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: inherit;
  font-size: 12px;
  font-weight: 720;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s, box-shadow 0.15s;
}

.chat-panel__style-pill span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-panel__style-pill:hover,
.chat-panel__style-pill--active {
  border-color: rgba(14, 165, 233, 0.46);
  color: #0284c7;
  background: rgba(240, 249, 255, 0.92);
  box-shadow: 0 8px 18px rgba(14, 165, 233, 0.1);
}

/* Style grid popover */
.chat-panel__style-popover {
  position: absolute;
  left: 0;
  bottom: calc(100% + 10px);
  width: 340px;
  padding: 12px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16), 0 0 0 1px rgba(255,255,255,0.6) inset;
  backdrop-filter: blur(20px);
  z-index: 10;
}

.chat-panel__style-popover-header {
  padding: 2px 4px 10px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.chat-panel__style-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.chat-panel__style-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  border: 1.5px solid rgba(226, 232, 240, 0.8);
  border-radius: 14px;
  padding: 6px 6px 8px;
  background: rgba(248, 250, 252, 0.6);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s, background 0.15s;
}

.chat-panel__style-card:hover {
  border-color: rgba(14, 165, 233, 0.4);
  background: rgba(240, 249, 255, 0.8);
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.1);
}

.chat-panel__style-card--selected {
  border-color: #0284c7;
  background: rgba(240, 249, 255, 0.9);
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.12);
}

.chat-panel__style-thumb {
  width: 100%;
  aspect-ratio: 16 / 10;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: -0.02em;
  overflow: hidden;
}

.chat-panel__style-thumb--none {
  background: linear-gradient(135deg, #e2e8f0, #f1f5f9);
  color: #94a3b8;
  font-weight: 700;
  font-size: 12px;
}

.chat-panel__style-thumb--0 { background: linear-gradient(135deg, #0ea5e9, #6366f1); }
.chat-panel__style-thumb--1 { background: linear-gradient(135deg, #1e1e2e, #3b0764); color: #e2e8f0; }
.chat-panel__style-thumb--2 { background: linear-gradient(135deg, #1d4ed8, #0f172a); }
.chat-panel__style-thumb--3 { background: linear-gradient(135deg, #f59e0b, #ec4899); }
.chat-panel__style-thumb--4 { background: linear-gradient(135deg, #10b981, #059669); }
.chat-panel__style-thumb--5 { background: linear-gradient(135deg, #8b5cf6, #ec4899); }

.chat-panel__style-label {
  color: #334155;
  font-size: 12px;
  font-weight: 650;
  text-align: center;
  line-height: 1.3;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-panel__style-card--selected .chat-panel__style-label {
  color: #0284c7;
}

/* Popover transition */
.popover-enter-active,
.popover-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.popover-enter-from,
.popover-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.chat-panel__send-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  border: none;
  background: linear-gradient(135deg, #0284c7, #6366f1);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 8px 20px rgba(2, 132, 199, 0.22);
  transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s;
}

.chat-panel__send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 12px 28px rgba(2, 132, 199, 0.3);
}

.chat-panel__send-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
  box-shadow: none;
}

@media (max-width: 1100px) {
  .chat-panel__workspace {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .chat-panel__conversation {
    min-height: 520px;
  }

  .chat-panel__preview {
    min-height: 520px;
  }
}

@media (max-width: 768px) {
  .chat-panel {
    height: 100%;
    min-height: 0;
  }

  .home-hero {
    min-height: 100%;
    padding: 18px 14px 14px;
    align-items: flex-start;
    overflow-y: auto;
  }

  .home-hero__content {
    max-width: none;
  }

  .home-hero__title {
    font-size: clamp(30px, 10vw, 42px);
  }

  .home-hero__subtitle {
    font-size: 14px;
  }

  .home-hero__composer {
    border-radius: 24px;
    padding: 14px;
  }

  .home-hero__composer-footer {
    align-items: flex-end;
  }

  .home-hero__tools {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .home-hero__device-toggle,
  .chat-panel__device-toggle {
    max-width: 100%;
    overflow-x: auto;
  }

  .chat-panel__toolbar {
    gap: 5px;
  }

  .chat-panel__device-option {
    min-height: 34px;
    padding: 7px 8px;
  }

  .home-hero__style-popover,
  .chat-panel__style-popover {
    left: 0;
    width: min(320px, calc(100vw - 32px));
  }

  .chat-panel__workspace {
    height: 100%;
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
    overflow: hidden;
    padding: 0;
  }

  .chat-panel__mobile-chat,
  .chat-panel__mobile-preview {
    display: none;
    height: 100%;
    min-height: 0;
  }

  .chat-panel__workspace--mobile-chat .chat-panel__mobile-chat,
  .chat-panel__workspace--mobile-preview .chat-panel__mobile-preview {
    display: flex;
  }

  .chat-panel__workspace--mobile-chat,
  .chat-panel__workspace--mobile-preview {
    display: flex;
  }

  .chat-panel__collapse-btn,
  .chat-panel__expand-btn {
    display: none;
  }

  .chat-panel__conversation,
  .chat-panel__preview {
    width: 100%;
    min-height: 0;
  }

  .chat-panel__conversation,
  .preview-card {
    border: none;
    border-radius: 0;
    box-shadow: none;
  }

  .chat-panel__messages {
    padding: 14px 12px;
    overscroll-behavior: contain;
  }

  .chat-panel__message-stream {
    gap: 10px;
  }

  .chat-panel__input-bar {
    padding: 8px 10px max(10px, env(safe-area-inset-bottom));
  }

  .chat-panel__input-box {
    border-radius: 20px;
  }

  .chat-panel__textarea {
    max-height: 120px;
    font-size: 16px;
  }

  .chat-panel__style-pill,
  .chat-panel__send-btn {
    min-width: 44px;
    min-height: 44px;
  }

  .chat-panel__style-pill {
    max-width: 112px;
    padding: 8px 10px;
  }

  .preview-card {
    height: 100%;
  }

  .preview-card__header {
    padding: 12px;
    gap: 10px;
  }

  .preview-card__header h2 {
    max-width: 58vw;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 16px;
  }

  .preview-card__open {
    min-height: 40px;
    padding: 10px 12px;
  }

  .preview-card__body {
    padding: 0;
  }

  .preview-card__iframe,
  .preview-card__placeholder {
    border: none;
    border-radius: 0;
    box-shadow: none;
  }

  .preview-card__placeholder {
    padding: 22px 16px;
  }
}
</style>
