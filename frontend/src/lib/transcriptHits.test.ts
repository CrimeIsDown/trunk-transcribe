import { afterEach, describe, expect, it, vi } from 'vitest'

import { createTranscriptHitTransformer } from './transcriptHits'

function createTranscriptHit() {
  return {
    _highlightResult: {
      transcript: {
        value: '<em>shots</em> fired',
      },
      raw_transcript: {
        value: JSON.stringify([
          [
            {
              filter_link: '#',
              src: 1234,
              label: 'Radio 1234',
              tag: 'Unit 12',
            },
            'shots fired\nnow',
          ],
        ]),
      },
    },
    audio_type: 'digital tdma',
    call_length: 30,
    id: 'abc123',
    raw_audio_url: 'https://example.com/audio.mp3',
    raw_metadata: JSON.stringify({
      encrypted: 1,
    }),
    raw_transcript: JSON.stringify([
      [
        {
          filter_link: '#',
          src: 1234,
          label: 'Radio 1234',
          tag: 'Unit 12',
        },
        'shots fired\nnow',
      ],
    ]),
    short_name: 'chi_cpd',
    start_time: 1_741_500_000,
    talkgroup: '5',
    talkgroup_description: 'Main Dispatch',
    talkgroup_group: 'Police',
    talkgroup_group_tag: 'Law Dispatch',
    talkgroup_tag: 'Zone 10',
  }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('transcriptHits', () => {
  it('builds transcript hit context, permalink, and source refinements', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-29T18:00:00Z'))

    const transformItems = createTranscriptHitTransformer({
      indexName: 'calls',
      hitsPerPage: 40,
      sortBy: 'calls:start_time:desc',
    })

    const [hit] = transformItems([createTranscriptHit()])

    const permalink = new URL(hit.permalink, 'http://localhost')
    const contextUrl = new URL(hit.contextUrl, 'http://localhost')

    expect(permalink.searchParams.get('calls[refinementList][talkgroup_tag][0]')).toBe(
      'Zone 10',
    )
    expect(permalink.searchParams.get('calls[range][start_time]')).toBe(
      '1741500000:1741500000',
    )
    expect(contextUrl.hash).toBe('#hit-abc123')
    expect(contextUrl.searchParams.get('calls[refinementList][talkgroup_tag][0]')).toBe(
      'Zone 10',
    )
    expect(contextUrl.searchParams.get('calls[range][start_time]')).toBe(
      '1741498800:1741500600',
    )
    expect(hit.talkgroup_group_tag_color).toBe('primary')
    expect(hit.encrypted).toBe(1)
    expect(hit.time_warning).toContain('delayed until')
    const sourceLink = new URL(hit.raw_transcript[0][0]?.filter_link || '', 'http://localhost')
    expect(
      sourceLink.searchParams.get('calls[refinementList][units][0]'),
    ).toBe('Unit 12')
    expect(hit.raw_transcript[0][0]?.label).toBe('Unit 12')
    expect(hit.raw_transcript[0][1]).toBe('shots fired<br>now')
  })
})
