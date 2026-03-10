const DEFAULT_INDEX_NAME = import.meta.env.VITE_MEILI_INDEX || 'calls'

export interface ScannerChatContext {
  talkgroupDescription: string
  radioSystem: string
  startDatetime: string
  endDatetime: string
}

export interface BuildScannerSearchUrlInput {
  query?: string
  talkgroupDescription?: string
  radioSystem?: string
  startDatetime?: string
  endDatetime?: string
  callId?: string
  callStartTime?: number
  indexName?: string
  hitsPerPage?: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function appendSearchParam(
  searchParams: URLSearchParams,
  key: string,
  value: unknown,
): void {
  if (value === undefined || value === null || value === '') {
    return
  }

  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      appendSearchParam(searchParams, `${key}[${index}]`, item)
    })
    return
  }

  if (isRecord(value)) {
    for (const [nestedKey, nestedValue] of Object.entries(value)) {
      appendSearchParam(searchParams, `${key}[${nestedKey}]`, nestedValue)
    }
    return
  }

  searchParams.append(key, String(value))
}

export function toEpochSeconds(value: string | undefined): number | undefined {
  if (!value) {
    return undefined
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return undefined
  }

  return Math.floor(parsed.getTime() / 1000)
}

export function toLocalDateTimeValue(value: Date): string {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  const hours = `${value.getHours()}`.padStart(2, '0')
  const minutes = `${value.getMinutes()}`.padStart(2, '0')
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

export function epochSecondsToLocalDateTimeValue(
  value: number | undefined,
): string {
  if (value === undefined || !Number.isFinite(value)) {
    return ''
  }

  return toLocalDateTimeValue(new Date(value * 1000))
}

function hashString(value: string): string {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

export function createScannerChatThreadId(context: ScannerChatContext): string {
  return `scanner-chat-${hashString(JSON.stringify(context))}`
}

export function buildScannerChatInstructions(
  context: ScannerChatContext,
): string {
  const talkgroupDescription = context.talkgroupDescription.trim()
  const radioSystem = context.radioSystem.trim()
  const startDatetime = context.startDatetime.trim()
  const endDatetime = context.endDatetime.trim()

  const scopeLines = ['Active transcript scope for this chat session:']

  if (talkgroupDescription) {
    scopeLines.push(`- Talkgroup description: ${talkgroupDescription}`)
  } else {
    scopeLines.push(
      '- Talkgroup description: not selected. Ask the user to confirm one unless they want an all-talkgroups search.',
    )
  }

  if (radioSystem) {
    scopeLines.push(`- Radio system: ${radioSystem}`)
  }

  if (startDatetime && endDatetime) {
    scopeLines.push(`- Time window: ${startDatetime} to ${endDatetime}`)
  }

  scopeLines.push(
    '- If the user wants to inspect results in the main search UI, use the frontend search navigation tools.',
  )

  return scopeLines.join('\n')
}

export function buildScannerSearchUrl(
  input: BuildScannerSearchUrlInput,
): string {
  const indexName = input.indexName || DEFAULT_INDEX_NAME
  const hitsPerPage = input.hitsPerPage || 60
  const query = input.query?.trim()
  const talkgroupDescription = input.talkgroupDescription?.trim()
  const radioSystem = input.radioSystem?.trim()

  const rangeStart =
    input.callStartTime !== undefined
      ? input.callStartTime - 60 * 20
      : toEpochSeconds(input.startDatetime)
  const rangeEnd =
    input.callStartTime !== undefined
      ? input.callStartTime + 60 * 10
      : toEpochSeconds(input.endDatetime)

  const indexState: Record<string, unknown> = {
    sortBy: `${indexName}:start_time:desc`,
    hitsPerPage,
  }

  if (query) {
    indexState.query = query
  }

  const refinementList: Record<string, string[]> = {}
  if (talkgroupDescription) {
    refinementList.talkgroup_description = [talkgroupDescription]
  }
  if (radioSystem) {
    refinementList.short_name = [radioSystem]
  }
  if (Object.keys(refinementList).length > 0) {
    indexState.refinementList = refinementList
  }

  if (rangeStart !== undefined || rangeEnd !== undefined) {
    indexState.range = {
      start_time: `${rangeStart ?? ''}:${rangeEnd ?? ''}`,
    }
  }

  const searchParams = new URLSearchParams()
  appendSearchParam(searchParams, indexName, indexState)

  const search = searchParams.toString()
  const hash = input.callId ? `#hit-${input.callId}` : ''

  if (!search) {
    return `/${hash}`
  }

  return `/?${search}${hash}`
}
