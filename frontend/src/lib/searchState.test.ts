import { describe, expect, it } from 'vitest'

import {
  buildScannerSearchUrl,
  createScannerChatThreadId,
} from './searchState'

describe('searchState', () => {
  it('builds scanner search urls with query, refinements, range, and hit anchors', () => {
    const relativeUrl = buildScannerSearchUrl({
      query: 'shots fired',
      talkgroupDescription: 'Main Dispatch',
      radioSystem: 'sys1',
      startDatetime: '2026-03-09T08:00',
      endDatetime: '2026-03-09T10:00',
      callId: 'abc123',
    })

    const url = new URL(relativeUrl, 'http://localhost')
    expect(url.pathname).toBe('/')
    expect(url.hash).toBe('#hit-abc123')
    expect(url.searchParams.get('calls[query]')).toBe('shots fired')
    expect(url.searchParams.get('calls[refinementList][talkgroup_description][0]')).toBe(
      'Main Dispatch',
    )
    expect(url.searchParams.get('calls[refinementList][short_name][0]')).toBe('sys1')
    expect(url.searchParams.get('calls[range][start_time]')).toMatch(/^\d+:\d+$/)
  })

  it('creates stable thread ids from the selected chat scope', () => {
    const baseContext = {
      talkgroupDescription: 'Main Dispatch',
      radioSystem: 'sys1',
      startDatetime: '2026-03-09T08:00',
      endDatetime: '2026-03-09T10:00',
    }

    expect(createScannerChatThreadId(baseContext)).toBe(
      createScannerChatThreadId(baseContext),
    )
    expect(
      createScannerChatThreadId({
        ...baseContext,
        talkgroupDescription: 'Citywide',
      }),
    ).not.toBe(createScannerChatThreadId(baseContext))
  })
})
