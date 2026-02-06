export interface Talkgroup {
  short_name: string
  talkgroup_group: string
  talkgroup_tag: string
  talkgroup_description?: string
  talkgroup: string
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
const apiKey = import.meta.env.VITE_API_KEY || ''

function authHeaders(): HeadersInit {
  const headers: HeadersInit = {}
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`
  }
  return headers
}

export async function fetchTalkgroups(): Promise<Talkgroup[]> {
  const response = await fetch(`${apiBaseUrl}/talkgroups`, {
    method: 'GET',
    headers: authHeaders(),
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch talkgroups (${response.status})`)
  }

  const payload = (await response.json()) as { talkgroups?: Talkgroup[] }
  return payload.talkgroups || []
}
