export type ChatRole = 'user' | 'assistant'

export interface ChatHistoryMessage {
  role: ChatRole
  content: string
}

export interface ChatRequestPayload {
  radio_channel: string
  start_datetime: string
  end_datetime: string
  question: string
  history: ChatHistoryMessage[]
  radio_system?: string
}

export interface ChatCitation {
  id: string
  start_time: string
  talkgroup_description: string
  search_url: string | null
}

export interface ChatResponsePayload {
  answer_markdown: string
  citations: ChatCitation[]
  result_count: number
  history: ChatHistoryMessage[]
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
const apiKey = import.meta.env.VITE_API_KEY || ''

function authHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  }
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`
  }
  return headers
}

export async function requestChatSummary(
  payload: ChatRequestPayload,
): Promise<ChatResponsePayload> {
  const response = await fetch(`${apiBaseUrl}/chat/transcript-summary`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const json = (await response.json()) as { detail?: string }
      if (json.detail) {
        detail = json.detail
      }
    } catch (_error) {
      // Keep generic message if JSON parsing fails.
    }
    throw new Error(detail)
  }

  return (await response.json()) as ChatResponsePayload
}
