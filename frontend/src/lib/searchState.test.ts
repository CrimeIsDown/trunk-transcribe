import { describe, expect, it } from 'vitest'

import {
  DEFAULT_MAX_ANALYSIS_HITS,
  buildScannerSearchUrl,
  createScannerChatThreadId,
  extractScannerSearchScope,
} from './searchState'

describe('searchState', () => {
  it('extracts a normalized scanner search scope from instantsearch ui state', () => {
    expect(
      extractScannerSearchScope({
        query: '  shots fired ',
        refinementList: {
          short_name: ['sys2', 'sys1', 'sys1'],
          talkgroup_tag: ['Zone 10'],
          ignored: ['value'],
        },
        hierarchicalMenu: {
          'talkgroup_hierarchy.lvl1': 'sys1 > Police',
          ignored: 'value',
        },
        range: {
          start_time: '1700000000:1700003600',
        },
        page: 4,
        hitsPerPage: 60,
        sortBy: 'calls:start_time:asc',
      }),
    ).toEqual({
      query: 'shots fired',
      refinementList: {
        short_name: ['sys1', 'sys2'],
        talkgroup_tag: ['Zone 10'],
      },
      hierarchicalMenu: {
        'talkgroup_hierarchy.lvl1': 'sys1 > Police',
      },
      range: {
        start_time: '1700000000:1700003600',
      },
      maxHits: DEFAULT_MAX_ANALYSIS_HITS,
    })
  })

  it('builds scanner search urls with full scope, range, and hit anchors', () => {
    const relativeUrl = buildScannerSearchUrl({
      scope: {
        query: 'shots fired',
        refinementList: {
          talkgroup_description: ['Main Dispatch'],
          short_name: ['sys1'],
        },
        hierarchicalMenu: {
          'talkgroup_hierarchy.lvl2': 'sys1 > Police > Main Dispatch',
        },
        range: {
          start_time: '1741500000:1741507200',
        },
      },
      callId: 'abc123',
      hitsPerPage: 40,
      sortBy: 'calls:start_time:asc',
    })

    const url = new URL(relativeUrl, 'http://localhost')
    expect(url.pathname).toBe('/')
    expect(url.hash).toBe('#hit-abc123')
    expect(url.searchParams.get('calls[query]')).toBe('shots fired')
    expect(url.searchParams.get('calls[refinementList][talkgroup_description][0]')).toBe(
      'Main Dispatch',
    )
    expect(url.searchParams.get('calls[refinementList][short_name][0]')).toBe('sys1')
    expect(url.searchParams.get('calls[hierarchicalMenu][talkgroup_hierarchy.lvl2]')).toBe(
      'sys1 > Police > Main Dispatch',
    )
    expect(url.searchParams.get('calls[range][start_time]')).toBe(
      '1741500000:1741507200',
    )
    expect(url.searchParams.get('calls[hitsPerPage]')).toBe('40')
    expect(url.searchParams.get('calls[sortBy]')).toBe('calls:start_time:asc')
  })

  it('creates stable thread ids from the normalized search scope', () => {
    const baseScope = {
      query: 'shots fired',
      refinementList: {
        short_name: ['sys1', 'sys2'],
      },
      range: {
        start_time: '1741500000:1741507200',
      },
    }

    expect(createScannerChatThreadId(baseScope)).toBe(
      createScannerChatThreadId({
        ...baseScope,
        refinementList: {
          short_name: ['sys2', 'sys1'],
        },
      }),
    )
    expect(
      createScannerChatThreadId({
        ...baseScope,
        query: 'vehicle pursuit',
      }),
    ).not.toBe(createScannerChatThreadId(baseScope))
  })
})
