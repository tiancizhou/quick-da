const BASE = "/api"

export interface App {
  id: string
  name: string
  status: "creating" | "editing" | "active" | "failed" | "edit_failed"
  progress?: string | null
  style_id?: string | null
  entry_path: string
  project_type: "html" | "project"
  visibility: "private" | "public" | "token"
  preview_token?: string | null
  opencode_session_id?: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface Style {
  id: string
  name: string
  prompt: string
  sort_order: number
  is_active?: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface Conversation {
  id: string
  app_id: string
  role: "user" | "assistant"
  content: string
  created_at: string
  updated_at: string
}

export interface CurrentUser {
  employee_no: string
  is_admin: boolean
}

export interface Employee {
  employee_no: string
  name: string
  status: "active" | "disabled"
  created_at: string
  updated_at: string
}

export interface UsageSummary {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  record_count: number
  estimated_record_count: number
  successful_record_count: number
  failed_record_count: number
  first_record_at?: string | null
  last_record_at?: string | null
}

export interface UsageRecord {
  id: string
  app_id?: string | null
  app_name?: string | null
  action: "name" | "generate" | "edit" | string
  provider: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost: number
  is_estimated: boolean
  status: "success" | "failed" | string
  created_at: string
  updated_at: string
}

export interface LLMSettingsSummary {
  base_url: string
  model: string
  api_key_configured: boolean
  api_key_masked?: string | null
  source: "database" | "env"
}

export interface LLMSettingsUpdate {
  base_url: string
  model: string
  api_key?: string
}

export type DevicePreference = "mobile" | "desktop" | "responsive"

export interface OpenCodeStreamEvent {
  type?: "opencode"
  kind: string
  [key: string]: unknown
}

export interface OpenCodeEventRecord {
  sequence: number
  event_type: string
  payload: OpenCodeStreamEvent
  created_at: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  })
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json()
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return request<CurrentUser>("/auth/me")
}

export async function login(employeeNo: string, password: string): Promise<CurrentUser> {
  return request<CurrentUser>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ employee_no: employeeNo, password }),
  })
}

export async function register(employeeNo: string, password: string): Promise<CurrentUser> {
  return request<CurrentUser>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ employee_no: employeeNo, password }),
  })
}

export async function logout(): Promise<void> {
  await request<{ ok: boolean }>("/auth/logout", { method: "POST" })
}

export async function listEmployees(): Promise<Employee[]> {
  return request<Employee[]>("/admin/employees")
}

export async function createEmployee(employeeNo: string, name: string): Promise<Employee> {
  return request<Employee>("/admin/employees", {
    method: "POST",
    body: JSON.stringify({ employee_no: employeeNo, name }),
  })
}

export async function disableEmployee(employeeNo: string): Promise<Employee> {
  return request<Employee>(`/admin/employees/${employeeNo}/disable`, { method: "POST" })
}

export async function listApps(): Promise<App[]> {
  return request<App[]>("/apps")
}

export async function createApp(styleId: string | null = null): Promise<App> {
  return request<App>("/apps", {
    method: "POST",
    body: JSON.stringify({ style_id: styleId }),
  })
}

export async function getApp(id: string): Promise<App> {
  return request<App>(`/apps/${id}`)
}

export async function deleteApp(id: string): Promise<void> {
  await request<{ ok: boolean }>(`/apps/${id}`, { method: "DELETE" })
}

export async function setAppStyle(appId: string, styleId: string | null): Promise<App> {
  return request<App>(`/apps/${appId}/style`, {
    method: "PATCH",
    body: JSON.stringify({ style_id: styleId }),
  })
}

export async function listStyles(): Promise<Style[]> {
  return request<Style[]>("/styles")
}

export async function listAdminStyles(): Promise<Style[]> {
  return request<Style[]>("/admin/styles")
}

export async function createStyle(data: { name: string; prompt: string; sort_order?: number }): Promise<Style> {
  return request<Style>("/admin/styles", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateStyle(id: string, data: Partial<Style>): Promise<Style> {
  return request<Style>(`/admin/styles/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })
}

export async function deleteStyle(id: string): Promise<void> {
  await request<{ ok: boolean }>(`/admin/styles/${id}`, { method: "DELETE" })
}

export async function getLLMSettings(): Promise<LLMSettingsSummary> {
  return request<LLMSettingsSummary>("/admin/llm-settings")
}

export async function updateLLMSettings(data: LLMSettingsUpdate): Promise<LLMSettingsSummary> {
  return request<LLMSettingsSummary>("/admin/llm-settings", {
    method: "PUT",
    body: JSON.stringify(data),
  })
}

export async function listConversations(appId: string): Promise<Conversation[]> {
  return request<Conversation[]>(`/apps/${appId}/conversations`)
}

export async function listOpenCodeEvents(appId: string): Promise<OpenCodeEventRecord[]> {
  return request<OpenCodeEventRecord[]>(`/apps/${appId}/opencode-events`)
}

export async function getAppPreview(appId: string): Promise<{ url: string }> {
  return request<{ url: string }>(`/apps/${appId}/preview`)
}

export async function getUsageSummary(): Promise<UsageSummary> {
  return request<UsageSummary>("/usage/summary")
}

export async function listUsageRecords(limit = 20, offset = 0): Promise<UsageRecord[]> {
  return request<UsageRecord[]>(`/usage/records?limit=${limit}&offset=${offset}`)
}

// Calls POST /api/apps/:id/chat via fetch with SSE parsing.
// onChunk(content) is called for each text chunk.
// onResult(url, status, error) is called when the result event arrives.
export async function sendChat(
  appId: string,
  message: string,
  devicePreference: DevicePreference,
  onChunk: (content: string) => void,
  onProgress: (progress: string) => void,
  onOpenCode: (event: OpenCodeStreamEvent) => void,
  onResult: (url: string | null, status: string, error?: string | null) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/apps/${appId}/chat`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, device_preference: devicePreference }),
  })

  if (!res.ok) throw new Error(`Chat request failed: ${res.status}`)
  if (!res.body) throw new Error("Response body is null")

  const reader = res.body.getReader()
  const decoder = new TextDecoder()

  let buffer = ""
  let currentEvent = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Process all complete lines in the buffer
    const lines = buffer.split("\n")
    // Keep the last (potentially incomplete) line in the buffer
    buffer = lines.pop() ?? ""

    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEvent = line.slice("event:".length).trim()
      } else if (line.startsWith("data:")) {
        const raw = line.slice("data:".length).trim()
        try {
          const parsed = JSON.parse(raw)
          if (currentEvent === "message") {
            onChunk(parsed.content ?? "")
          } else if (currentEvent === "progress") {
            onProgress(parsed.content ?? "")
          } else if (currentEvent === "opencode") {
            onOpenCode(parsed)
          } else if (currentEvent === "result") {
            onResult(parsed.url ?? null, parsed.status ?? "failed", parsed.error ?? null)
          }
        } catch {
          // Ignore malformed JSON
        }
        // Reset event name after dispatching
        currentEvent = ""
      }
      // Blank lines are natural SSE separators; we reset event on data dispatch above
    }
  }

  // Flush any remaining buffer content
  if (buffer.trim()) {
    if (buffer.startsWith("data:")) {
      const raw = buffer.slice("data:".length).trim()
      try {
        const parsed = JSON.parse(raw)
        if (currentEvent === "message") {
          onChunk(parsed.content ?? "")
        } else if (currentEvent === "opencode") {
          onOpenCode(parsed)
        } else if (currentEvent === "result") {
          onResult(parsed.url ?? null, parsed.status ?? "failed", parsed.error ?? null)
        }
      } catch {
        // Ignore
      }
    }
  }
}
