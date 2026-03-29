import {
  buildScannerSearchUrl,
  describeScannerSearchScope,
  extractScannerSearchUiState,
  type ScannerSearchUiState,
} from './searchState'

export interface TranscriptSavedSearchEntry {
  id: string
  name: string
  state: ScannerSearchUiState
  createdAt: string
  updatedAt: string
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'> &
  Partial<Pick<Storage, 'removeItem'>>

const STORAGE_KEY = 'crimeisdown.transcriptSavedSearches.v1'

function getStorage(storage?: StorageLike): StorageLike | undefined {
  if (storage) {
    return storage
  }

  if (typeof window === 'undefined') {
    return undefined
  }

  return window.localStorage
}

function generateSavedSearchId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `saved-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function normalizeSavedSearchName(name: string): string {
  return name.trim()
}

function normalizeSavedSearchState(
  indexUiState: Record<string, unknown> | undefined,
): ScannerSearchUiState {
  return extractScannerSearchUiState(indexUiState)
}

function parseSavedSearchEntry(value: unknown): TranscriptSavedSearchEntry | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null
  }

  const candidate = value as Partial<TranscriptSavedSearchEntry>
  if (
    typeof candidate.id !== 'string' ||
    typeof candidate.name !== 'string' ||
    typeof candidate.createdAt !== 'string' ||
    typeof candidate.updatedAt !== 'string' ||
    typeof candidate.state !== 'object' ||
    candidate.state === null ||
    Array.isArray(candidate.state)
  ) {
    return null
  }

  const name = normalizeSavedSearchName(candidate.name)
  if (!name) {
    return null
  }

  return {
    id: candidate.id,
    name,
    createdAt: candidate.createdAt,
    updatedAt: candidate.updatedAt,
    state: normalizeSavedSearchState(candidate.state as Record<string, unknown>),
  }
}

function sortSavedSearches(
  entries: TranscriptSavedSearchEntry[],
): TranscriptSavedSearchEntry[] {
  return [...entries].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  )
}

function readSavedSearchPayload(storage: StorageLike | undefined): unknown[] {
  if (!storage) {
    return []
  }

  const rawValue = storage.getItem(STORAGE_KEY)
  if (!rawValue) {
    return []
  }

  try {
    const parsed = JSON.parse(rawValue)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function extractTranscriptSavedSearchState(
  indexUiState: Record<string, unknown> | undefined,
): ScannerSearchUiState {
  return normalizeSavedSearchState(indexUiState)
}

export function describeTranscriptSavedSearchState(
  state: ScannerSearchUiState,
): string[] {
  const summary = describeScannerSearchScope(state)
  if (state.sortBy) {
    summary.push(`Sort: ${state.sortBy}`)
  }
  if (state.hitsPerPage) {
    summary.push(`Results per page: ${state.hitsPerPage}`)
  }
  return summary
}

export function buildTranscriptSavedSearchUrl(
  indexName: string,
  state: ScannerSearchUiState,
): string {
  return buildScannerSearchUrl({
    indexName,
    scope: state,
    hitsPerPage: state.hitsPerPage,
    sortBy: state.sortBy,
  })
}

export function loadTranscriptSavedSearches(
  storage?: StorageLike,
): TranscriptSavedSearchEntry[] {
  const activeStorage = getStorage(storage)
  return sortSavedSearches(
    readSavedSearchPayload(activeStorage)
      .map(parseSavedSearchEntry)
      .filter(
        (entry): entry is TranscriptSavedSearchEntry => entry !== null,
      ),
  )
}

export function persistTranscriptSavedSearches(
  entries: TranscriptSavedSearchEntry[],
  storage?: StorageLike,
): TranscriptSavedSearchEntry[] {
  const normalizedEntries = sortSavedSearches(entries)
  const activeStorage = getStorage(storage)
  activeStorage?.setItem(STORAGE_KEY, JSON.stringify(normalizedEntries))
  return normalizedEntries
}

export function createTranscriptSavedSearchEntry(
  name: string,
  indexUiState: Record<string, unknown> | undefined,
): TranscriptSavedSearchEntry {
  const now = new Date().toISOString()
  return {
    id: generateSavedSearchId(),
    name: normalizeSavedSearchName(name),
    state: extractTranscriptSavedSearchState(indexUiState),
    createdAt: now,
    updatedAt: now,
  }
}

export function updateTranscriptSavedSearchEntry(
  entry: TranscriptSavedSearchEntry,
  indexUiState: Record<string, unknown> | undefined,
): TranscriptSavedSearchEntry {
  const now = new Date().toISOString()
  return {
    ...entry,
    state: extractTranscriptSavedSearchState(indexUiState),
    updatedAt: now,
  }
}

export function upsertTranscriptSavedSearchEntry(
  entries: TranscriptSavedSearchEntry[],
  nextEntry: TranscriptSavedSearchEntry,
): TranscriptSavedSearchEntry[] {
  return sortSavedSearches([
    ...entries.filter((entry) => entry.id !== nextEntry.id),
    nextEntry,
  ])
}

export function deleteTranscriptSavedSearchEntry(
  entries: TranscriptSavedSearchEntry[],
  id: string,
): TranscriptSavedSearchEntry[] {
  return sortSavedSearches(entries.filter((entry) => entry.id !== id))
}

