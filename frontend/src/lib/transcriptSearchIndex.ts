import {
  buildScannerSearchUrl,
  type ScannerSearchScope,
} from './searchState'

const DEFAULT_BASE_INDEX_NAME = import.meta.env.VITE_MEILI_INDEX || 'calls'
const DEFAULT_SPLIT_BY_MONTH =
  import.meta.env.VITE_MEILI_INDEX_SPLIT_BY_MONTH === 'true'

export interface TranscriptSearchIndexConfig {
  baseIndexName?: string
  splitByMonth?: boolean
  referenceDate?: Date
}

export interface TranscriptSearchRange {
  start_time?: string
}

export interface BuildTranscriptArchiveSearchUrlInput {
  currentIndexName: string
  nextIndexName: string
  scope: ScannerSearchScope
  hitsPerPage?: number
  sortBy?: string
  hash?: string
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function normalizeConfig(
  config?: TranscriptSearchIndexConfig,
): Required<Omit<TranscriptSearchIndexConfig, 'referenceDate'>> & {
  referenceDate: Date
} {
  return {
    baseIndexName: config?.baseIndexName || DEFAULT_BASE_INDEX_NAME,
    splitByMonth: config?.splitByMonth ?? DEFAULT_SPLIT_BY_MONTH,
    referenceDate: config?.referenceDate || new Date(),
  }
}

function parseMonthIndexName(
  indexName: string,
  baseIndexName: string,
): { year: number; month: number } | null {
  const match = new RegExp(
    `^${escapeRegExp(baseIndexName)}_(\\d{4})_(\\d{2})$`,
  ).exec(indexName)

  if (!match) {
    return null
  }

  const year = Number.parseInt(match[1], 10)
  const month = Number.parseInt(match[2], 10)

  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) {
    return null
  }

  return { year, month }
}

export function getTranscriptMonthIndexName(
  baseIndexName: string,
  referenceDate = new Date(),
): string {
  const year = referenceDate.getFullYear()
  const month = `${referenceDate.getMonth() + 1}`.padStart(2, '0')
  return `${baseIndexName}_${year}_${month}`
}

export function getTranscriptCurrentMonthIndexName(
  config?: TranscriptSearchIndexConfig,
): string {
  const normalized = normalizeConfig(config)
  return getTranscriptMonthIndexName(
    normalized.baseIndexName,
    normalized.referenceDate,
  )
}

export function isTranscriptMonthlyIndexName(
  indexName: string,
  baseIndexName?: string,
): boolean {
  const normalizedBaseIndexName = baseIndexName || DEFAULT_BASE_INDEX_NAME
  return parseMonthIndexName(indexName, normalizedBaseIndexName) !== null
}

export function getTranscriptSearchIndexNameFromLocation(
  search: string,
  config?: TranscriptSearchIndexConfig,
): string {
  const normalized = normalizeConfig(config)

  const searchParams = new URLSearchParams(
    search.startsWith('?') ? search.slice(1) : search,
  )
  for (const key of searchParams.keys()) {
    const bracketIndex = key.indexOf('[')
    if (bracketIndex === -1) {
      continue
    }

    const candidate = key.slice(0, bracketIndex)
    if (!candidate) {
      continue
    }

    if (isTranscriptMonthlyIndexName(candidate, normalized.baseIndexName)) {
      return candidate
    }

    if (!normalized.splitByMonth && candidate === normalized.baseIndexName) {
      return candidate
    }
  }

  return normalized.splitByMonth
    ? getTranscriptCurrentMonthIndexName(normalized)
    : normalized.baseIndexName
}

export function getTranscriptSearchIndexNameForRange(
  range: TranscriptSearchRange | undefined,
  config?: TranscriptSearchIndexConfig,
): string {
  const normalized = normalizeConfig(config)

  if (!normalized.splitByMonth) {
    return normalized.baseIndexName
  }

  const startRaw = range?.start_time?.split(':', 2)[0]
  const startEpochSeconds = Number.parseInt(startRaw || '', 10)
  if (!Number.isFinite(startEpochSeconds)) {
    return getTranscriptCurrentMonthIndexName(normalized)
  }

  return getTranscriptMonthIndexName(
    normalized.baseIndexName,
    new Date(startEpochSeconds * 1000),
  )
}

export function getTranscriptMonthRangeBounds(
  referenceDate: Date,
): { start_time: number; end_time: number } {
  const start = new Date(
    referenceDate.getFullYear(),
    referenceDate.getMonth(),
    1,
    0,
    0,
    0,
    0,
  )
  const end = new Date(
    referenceDate.getFullYear(),
    referenceDate.getMonth() + 1,
    0,
    23,
    59,
    59,
    999,
  )

  return {
    start_time: Math.floor(start.getTime() / 1000),
    end_time: Math.floor(end.getTime() / 1000),
  }
}

export function clampTranscriptSearchRangeToMonth(
  range: string | undefined,
): string | undefined {
  if (!range) {
    return undefined
  }

  const [startRaw, endRaw] = range.split(':', 2)
  const startEpochSeconds = Number.parseInt(startRaw || '', 10)
  if (!Number.isFinite(startEpochSeconds)) {
    return range
  }

  const monthBounds = getTranscriptMonthRangeBounds(
    new Date(startEpochSeconds * 1000),
  )
  const endEpochSeconds = Number.parseInt(endRaw || '', 10)

  if (!Number.isFinite(endEpochSeconds)) {
    return `${monthBounds.start_time}:${monthBounds.end_time}`
  }

  return `${monthBounds.start_time}:${Math.min(
    endEpochSeconds,
    monthBounds.end_time,
  )}`
}

export function rewriteTranscriptSortByIndexName(
  sortBy: string | undefined,
  nextIndexName: string,
  previousIndexName?: string,
): string | undefined {
  if (!sortBy) {
    return undefined
  }

  const currentPrefix = previousIndexName || DEFAULT_BASE_INDEX_NAME
  if (!sortBy.startsWith(`${currentPrefix}:`)) {
    return sortBy
  }

  return `${nextIndexName}${sortBy.slice(currentPrefix.length)}`
}

export function buildTranscriptArchiveSearchUrl({
  currentIndexName,
  nextIndexName,
  scope,
  hitsPerPage,
  sortBy,
  hash,
}: BuildTranscriptArchiveSearchUrlInput): string {
  const nextUrl = buildScannerSearchUrl({
    indexName: nextIndexName,
    scope,
    hitsPerPage,
    sortBy:
      rewriteTranscriptSortByIndexName(
        sortBy,
        nextIndexName,
        currentIndexName,
      ) ?? `${nextIndexName}:start_time:desc`,
  })

  return hash ? `${nextUrl}${hash}` : nextUrl
}
