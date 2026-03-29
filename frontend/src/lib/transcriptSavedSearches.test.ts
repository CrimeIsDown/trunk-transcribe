import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildTranscriptSavedSearchUrl,
  createTranscriptSavedSearchEntry,
  deleteTranscriptSavedSearchEntry,
  describeTranscriptSavedSearchState,
  extractTranscriptSavedSearchState,
  loadTranscriptSavedSearches,
  persistTranscriptSavedSearches,
  updateTranscriptSavedSearchEntry,
  upsertTranscriptSavedSearchEntry,
} from './transcriptSavedSearches'

type MemoryStorage = {
  data: Record<string, string>
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
}

function createMemoryStorage(): MemoryStorage {
  return {
    data: {},
    getItem(key) {
      return Object.prototype.hasOwnProperty.call(this.data, key)
        ? this.data[key]
        : null
    },
    setItem(key, value) {
      this.data[key] = value
    },
  }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('transcriptSavedSearches', () => {
  it('normalizes saved search state and keeps sort plus page size', () => {
    expect(
      extractTranscriptSavedSearchState({
        query: ' shots fired ',
        refinementList: {
          short_name: ['sys2', 'sys1'],
        },
        hierarchicalMenu: {
          'talkgroup_hierarchy.lvl2': 'sys1 > Police > Main Dispatch',
        },
        range: {
          start_time: '1700000000:1700003600',
        },
        sortBy: ' calls:start_time:asc ',
        hitsPerPage: 40,
        maxHits: 25,
      }),
    ).toEqual({
      query: 'shots fired',
      refinementList: {
        short_name: ['sys1', 'sys2'],
      },
      hierarchicalMenu: {
        'talkgroup_hierarchy.lvl2': 'sys1 > Police > Main Dispatch',
      },
      range: {
        start_time: '1700000000:1700003600',
      },
      sortBy: 'calls:start_time:asc',
      hitsPerPage: 40,
    })
  })

  it('round-trips saved searches through storage in a stable order', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-29T18:00:00Z'))

    const storage = createMemoryStorage()
    const created = createTranscriptSavedSearchEntry('  Shots Fired  ', {
      query: 'shots fired',
      refinementList: {
        short_name: ['sys1'],
      },
      sortBy: 'calls:start_time:desc',
      hitsPerPage: 40,
    })

    expect(created.name).toBe('Shots Fired')
    expect(created.createdAt).toBe('2026-03-29T18:00:00.000Z')
    expect(created.updatedAt).toBe('2026-03-29T18:00:00.000Z')

    const persisted = persistTranscriptSavedSearches([created], storage)
    expect(persisted).toHaveLength(1)
    expect(loadTranscriptSavedSearches(storage)).toEqual(persisted)

    expect(
      describeTranscriptSavedSearchState(persisted[0].state),
    ).toContain('Sort: calls:start_time:desc')

    expect(
      new URL(buildTranscriptSavedSearchUrl('calls', persisted[0].state), 'http://localhost')
        .searchParams.get('calls[sortBy]'),
    ).toBe('calls:start_time:desc')
  })

  it('updates and deletes saved searches by id', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-29T18:00:00Z'))

    const created = createTranscriptSavedSearchEntry('Shots Fired', {
      query: 'shots fired',
    })
    vi.setSystemTime(new Date('2026-03-29T18:30:00Z'))
    const updated = updateTranscriptSavedSearchEntry(created, {
      query: 'vehicle pursuit',
      hitsPerPage: 20,
    })

    expect(updated.createdAt).toBe(created.createdAt)
    expect(updated.updatedAt).toBe('2026-03-29T18:30:00.000Z')
    expect(updated.state.query).toBe('vehicle pursuit')
    expect(updated.state.hitsPerPage).toBe(20)

    const entries = upsertTranscriptSavedSearchEntry([created], updated)
    expect(entries).toEqual([updated])
    expect(deleteTranscriptSavedSearchEntry(entries, updated.id)).toEqual([])
  })
})
