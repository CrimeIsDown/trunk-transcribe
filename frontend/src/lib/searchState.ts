const DEFAULT_INDEX_NAME = import.meta.env.VITE_MEILI_INDEX || 'calls'
export const DEFAULT_MAX_ANALYSIS_HITS = 200

const SUPPORTED_REFINEMENT_ATTRIBUTES = [
  'radios',
  'short_name',
  'talkgroup_description',
  'talkgroup_group',
  'talkgroup_group_tag',
  'talkgroup_tag',
  'units',
] as const

const SUPPORTED_HIERARCHICAL_ATTRIBUTES = [
  'talkgroup_hierarchy.lvl0',
  'talkgroup_hierarchy.lvl1',
  'talkgroup_hierarchy.lvl2',
] as const

type SupportedRefinementAttribute =
  (typeof SUPPORTED_REFINEMENT_ATTRIBUTES)[number]
type SupportedHierarchicalAttribute =
  (typeof SUPPORTED_HIERARCHICAL_ATTRIBUTES)[number]

export interface ScannerSearchScope {
  query?: string
  refinementList?: Partial<Record<SupportedRefinementAttribute, string[]>>
  hierarchicalMenu?: Partial<Record<SupportedHierarchicalAttribute, string>>
  range?: {
    start_time?: string
  }
  maxHits?: number
}

export interface ScannerSearchUiState
  extends Omit<ScannerSearchScope, 'maxHits'> {
  hitsPerPage?: number
  sortBy?: string
}

export interface BuildScannerSearchUrlInput {
  scope?: ScannerSearchScope
  callId?: string
  callStartTime?: number
  focusWindowSeconds?: number
  indexName?: string
  hitsPerPage?: number
  sortBy?: string
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

function sortRecord<T extends string | string[]>(
  value: Record<string, T> | undefined,
): Record<string, T> | undefined {
  if (!value) {
    return undefined
  }

  const entries = Object.entries(value).sort(([left], [right]) =>
    left.localeCompare(right),
  )
  if (entries.length === 0) {
    return undefined
  }

  return Object.fromEntries(entries)
}

function normalizeStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined
  }

  const normalized = Array.from(
    new Set(
      value
        .map((item) => (typeof item === 'string' ? item.trim() : ''))
        .filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right))

  return normalized.length > 0 ? normalized : undefined
}

function normalizeRangeValue(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined
  }

  const trimmed = value.trim()
  if (!trimmed || !trimmed.includes(':')) {
    return undefined
  }
  return trimmed
}

function normalizeSortByValue(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined
  }

  const trimmed = value.trim()
  return trimmed ? trimmed : undefined
}

function normalizeHitsPerPageValue(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return undefined
  }

  const normalized = Math.floor(value)
  return normalized > 0 ? normalized : undefined
}

function normalizeSearchScope(scope: ScannerSearchScope): ScannerSearchScope {
  const normalizedRefinementList = sortRecord(
    Object.fromEntries(
      SUPPORTED_REFINEMENT_ATTRIBUTES.flatMap((attribute) => {
        const values = normalizeStringArray(scope.refinementList?.[attribute])
        return values ? [[attribute, values]] : []
      }),
    ) as ScannerSearchScope['refinementList'],
  )

  const normalizedHierarchicalMenu = sortRecord(
    Object.fromEntries(
      SUPPORTED_HIERARCHICAL_ATTRIBUTES.flatMap((attribute) => {
        const value = scope.hierarchicalMenu?.[attribute]?.trim()
        return value ? [[attribute, value]] : []
      }),
    ) as ScannerSearchScope['hierarchicalMenu'],
  )

  const normalizedRange = normalizeRangeValue(scope.range?.start_time)
    ? { start_time: normalizeRangeValue(scope.range?.start_time) }
    : undefined

  const query = scope.query?.trim()

  return {
    ...(query ? { query } : {}),
    ...(normalizedRefinementList ? { refinementList: normalizedRefinementList } : {}),
    ...(normalizedHierarchicalMenu
      ? { hierarchicalMenu: normalizedHierarchicalMenu }
      : {}),
    ...(normalizedRange ? { range: normalizedRange } : {}),
    ...(scope.maxHits ? { maxHits: scope.maxHits } : {}),
  }
}

export function extractScannerSearchScope(
  indexUiState: Record<string, unknown> | undefined,
  maxHits: number = DEFAULT_MAX_ANALYSIS_HITS,
): ScannerSearchScope {
  const refinementList = isRecord(indexUiState?.refinementList)
    ? (indexUiState?.refinementList as Record<string, unknown>)
    : undefined
  const hierarchicalMenu = isRecord(indexUiState?.hierarchicalMenu)
    ? (indexUiState?.hierarchicalMenu as Record<string, unknown>)
    : undefined
  const range = isRecord(indexUiState?.range)
    ? (indexUiState?.range as Record<string, unknown>)
    : undefined

  return normalizeSearchScope({
    query: typeof indexUiState?.query === 'string' ? indexUiState.query : undefined,
    refinementList: Object.fromEntries(
      SUPPORTED_REFINEMENT_ATTRIBUTES.flatMap((attribute) => {
        const values = normalizeStringArray(refinementList?.[attribute])
        return values ? [[attribute, values]] : []
      }),
    ),
    hierarchicalMenu: Object.fromEntries(
      SUPPORTED_HIERARCHICAL_ATTRIBUTES.flatMap((attribute) => {
        const value =
          typeof hierarchicalMenu?.[attribute] === 'string'
            ? hierarchicalMenu[attribute].trim()
            : ''
        return value ? [[attribute, value]] : []
      }),
    ),
    range: {
      start_time: normalizeRangeValue(range?.start_time),
    },
    maxHits,
  })
}

export function extractScannerSearchUiState(
  indexUiState: Record<string, unknown> | undefined,
): ScannerSearchUiState {
  const scope = extractScannerSearchScope(indexUiState)
  const { maxHits: _maxHits, ...savedScope } = scope
  const sortBy = normalizeSortByValue(indexUiState?.sortBy)
  const hitsPerPage = normalizeHitsPerPageValue(indexUiState?.hitsPerPage)

  return {
    ...savedScope,
    ...(sortBy ? { sortBy } : {}),
    ...(hitsPerPage ? { hitsPerPage } : {}),
  }
}

export function createScannerChatThreadId(scope: ScannerSearchScope): string {
  return `scanner-chat-${hashString(JSON.stringify(normalizeSearchScope(scope)))}`
}

function summarizeRange(range: string | undefined): string | undefined {
  if (!range) {
    return undefined
  }

  const [start, end] = range.split(':', 2)
  const startValue = epochSecondsToLocalDateTimeValue(Number(start))
  const endValue = epochSecondsToLocalDateTimeValue(Number(end))
  if (!startValue && !endValue) {
    return undefined
  }
  return `${startValue || 'open'} to ${endValue || 'open'}`
}

export function describeScannerSearchScope(scope: ScannerSearchScope): string[] {
  const normalizedScope = normalizeSearchScope(scope)
  const summary: string[] = []

  if (normalizedScope.query) {
    summary.push(`Query: ${normalizedScope.query}`)
  }

  for (const attribute of SUPPORTED_REFINEMENT_ATTRIBUTES) {
    const values = normalizedScope.refinementList?.[attribute]
    if (values?.length) {
      summary.push(`${attribute}: ${values.join(', ')}`)
    }
  }

  for (const attribute of SUPPORTED_HIERARCHICAL_ATTRIBUTES) {
    const value = normalizedScope.hierarchicalMenu?.[attribute]
    if (value) {
      summary.push(`${attribute}: ${value}`)
    }
  }

  const rangeSummary = summarizeRange(normalizedScope.range?.start_time)
  if (rangeSummary) {
    summary.push(`Time: ${rangeSummary}`)
  }

  return summary
}

export function isBroadScannerSearchScope(scope: ScannerSearchScope): boolean {
  const normalizedScope = normalizeSearchScope(scope)
  return (
    !normalizedScope.query &&
    !normalizedScope.range?.start_time &&
    !normalizedScope.refinementList &&
    !normalizedScope.hierarchicalMenu
  )
}

export function buildScannerChatInstructions(scope: ScannerSearchScope): string {
  const normalizedScope = normalizeSearchScope(scope)
  const scopeLines = ['Active transcript search scope for this chat session:']

  const scopeSummary = describeScannerSearchScope(normalizedScope)
  if (scopeSummary.length === 0) {
    scopeLines.push('- No active query or refinements are applied yet.')
  } else {
    scopeSummary.forEach((line) => scopeLines.push(`- ${line}`))
  }

  scopeLines.push(
    `- Maximum transcript analysis depth: ${normalizedScope.maxHits || DEFAULT_MAX_ANALYSIS_HITS} matching calls.`,
  )
  scopeLines.push(
    '- Call `get_current_search_scope` before transcript analysis unless the user explicitly asks to change filters.',
  )
  scopeLines.push(
    '- Use `search_transcripts` with that exact scope so your evidence matches the visible search results.',
  )
  scopeLines.push(
    '- If the user wants to inspect evidence in the main search UI, use the frontend search navigation tools.',
  )
  scopeLines.push(`Exact scope JSON: ${JSON.stringify(normalizedScope)}`)

  return scopeLines.join('\n')
}

export function buildScannerSearchUrl(
  input: BuildScannerSearchUrlInput,
): string {
  const scope = normalizeSearchScope(input.scope || {})
  const indexName = input.indexName || DEFAULT_INDEX_NAME
  const hitsPerPage = input.hitsPerPage || 60
  const focusWindowSeconds = input.focusWindowSeconds || 30 * 60
  const sortBy = input.sortBy || `${indexName}:start_time:desc`

  const indexState: Record<string, unknown> = {
    sortBy,
    hitsPerPage,
  }

  if (scope.query) {
    indexState.query = scope.query
  }

  if (scope.refinementList && Object.keys(scope.refinementList).length > 0) {
    indexState.refinementList = scope.refinementList
  }

  if (scope.hierarchicalMenu && Object.keys(scope.hierarchicalMenu).length > 0) {
    indexState.hierarchicalMenu = scope.hierarchicalMenu
  }

  if (scope.range?.start_time) {
    indexState.range = scope.range
  } else if (input.callStartTime !== undefined) {
    indexState.range = {
      start_time: `${input.callStartTime - focusWindowSeconds}:${input.callStartTime + focusWindowSeconds}`,
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
