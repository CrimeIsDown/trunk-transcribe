import { describe, expect, it } from 'vitest'

import {
  buildTranscriptArchiveSearchUrl,
  clampTranscriptSearchRangeToMonth,
  getTranscriptCurrentMonthIndexName,
  getTranscriptMonthRangeBounds,
  getTranscriptMonthIndexName,
  getTranscriptSearchIndexNameForRange,
  getTranscriptSearchIndexNameFromLocation,
  isTranscriptMonthlyIndexName,
  rewriteTranscriptSortByIndexName,
} from './transcriptSearchIndex'

describe('transcriptSearchIndex', () => {
  const referenceDate = new Date('2026-03-15T12:00:00Z')

  it('recognizes and derives monthly index names', () => {
    expect(getTranscriptMonthIndexName('calls', referenceDate)).toBe(
      'calls_2026_03',
    )
    expect(
      getTranscriptCurrentMonthIndexName({
        baseIndexName: 'calls',
        splitByMonth: true,
        referenceDate,
      }),
    ).toBe('calls_2026_03')
    expect(isTranscriptMonthlyIndexName('calls_2026_03', 'calls')).toBe(true)
    expect(isTranscriptMonthlyIndexName('calls', 'calls')).toBe(false)
  })

  it('selects an archive index from location and range state', () => {
    expect(
      getTranscriptSearchIndexNameFromLocation('?calls[query]=shots', {
        baseIndexName: 'calls',
        splitByMonth: true,
        referenceDate,
      }),
    ).toBe('calls_2026_03')
    expect(
      getTranscriptSearchIndexNameFromLocation('?calls_2026_03[query]=shots', {
        baseIndexName: 'calls',
        splitByMonth: true,
        referenceDate,
      }),
    ).toBe('calls_2026_03')

    const marchStart = Math.floor(Date.parse('2026-03-18T05:00:00Z') / 1000)
    expect(
      getTranscriptSearchIndexNameForRange(
        {
          start_time: `${marchStart}:${marchStart + 3600}`,
        },
        {
          baseIndexName: 'calls',
          splitByMonth: true,
          referenceDate,
        },
      ),
    ).toBe('calls_2026_03')
  })

  it('clamps ranges and rewrites archive urls', () => {
    const start = Math.floor(Date.parse('2026-03-18T05:00:00Z') / 1000)
    const end = Math.floor(Date.parse('2026-04-02T05:00:00Z') / 1000)
    const monthBounds = getTranscriptMonthRangeBounds(new Date(start * 1000))

    expect(clampTranscriptSearchRangeToMonth(`${start}:${end}`)).toBe(
      `${monthBounds.start_time}:${monthBounds.end_time}`,
    )

    expect(rewriteTranscriptSortByIndexName('calls:start_time:desc', 'calls_2026_03', 'calls')).toBe(
      'calls_2026_03:start_time:desc',
    )

    const archiveUrl = buildTranscriptArchiveSearchUrl({
      currentIndexName: 'calls',
      nextIndexName: 'calls_2026_03',
      scope: {
        query: 'shots fired',
        range: {
          start_time: clampTranscriptSearchRangeToMonth(`${start}:${end}`),
        },
      },
      hitsPerPage: 40,
      sortBy: 'calls:start_time:desc',
      hash: '#hit-123',
    })

    const parsed = new URL(archiveUrl, 'http://localhost')
    expect(parsed.searchParams.get('calls_2026_03[query]')).toBe('shots fired')
    expect(parsed.searchParams.get('calls_2026_03[range][start_time]')).toBe(
      `${monthBounds.start_time}:${monthBounds.end_time}`,
    )
    expect(parsed.searchParams.get('calls_2026_03[hitsPerPage]')).toBe('40')
    expect(parsed.searchParams.get('calls_2026_03[sortBy]')).toBe(
      'calls_2026_03:start_time:desc',
    )
    expect(parsed.hash).toBe('#hit-123')
  })
})
