// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ChatPage from './ChatPage'
import { requestChatSummary } from '@/lib/chatApi'
import { fetchTalkgroups } from '@/lib/talkgroupsApi'

vi.mock('@/lib/chatApi', () => ({
  requestChatSummary: vi.fn(),
}))

vi.mock('@/lib/talkgroupsApi', () => ({
  fetchTalkgroups: vi.fn(),
}))

const mockedRequestChatSummary = vi.mocked(requestChatSummary)
const mockedFetchTalkgroups = vi.mocked(fetchTalkgroups)

describe('ChatPage', () => {
  beforeEach(() => {
    mockedRequestChatSummary.mockReset()
    mockedFetchTalkgroups.mockReset()
    mockedFetchTalkgroups.mockResolvedValue([
      {
        short_name: 'sys1',
        talkgroup_group: 'group',
        talkgroup_tag: 'tag',
        talkgroup_description: 'Main Dispatch',
        talkgroup: '1',
      },
      {
        short_name: 'sys1',
        talkgroup_group: 'group',
        talkgroup_tag: 'tag2',
        talkgroup_description: 'Main Dispatch',
        talkgroup: '2',
      },
      {
        short_name: 'sys2',
        talkgroup_group: 'group',
        talkgroup_tag: 'tag3',
        talkgroup_description: 'Citywide',
        talkgroup: '3',
      },
    ])
  })

  it('prefills a default last-two-hours window', async () => {
    render(<ChatPage />)

    const startInput = screen.getByLabelText('Start time') as HTMLInputElement
    const endInput = screen.getByLabelText('End time') as HTMLInputElement
    expect(startInput.value.length).toBeGreaterThan(0)
    expect(endInput.value.length).toBeGreaterThan(0)

    const start = new Date(startInput.value)
    const end = new Date(endInput.value)
    const diffMinutes = (end.getTime() - start.getTime()) / (60 * 1000)
    expect(diffMinutes).toBeGreaterThanOrEqual(119)
    expect(diffMinutes).toBeLessThanOrEqual(121)

    await waitFor(() => {
      expect(mockedFetchTalkgroups).toHaveBeenCalledTimes(1)
    })
  })

  it('loads unique channel suggestions for autocomplete', async () => {
    render(<ChatPage />)

    await waitFor(() => {
      const options = document.querySelectorAll('#channel-suggestions option')
      expect(options.length).toBe(2)
    })
  })

  it('sends history for follow-up and resets when filters change', async () => {
    mockedRequestChatSummary
      .mockResolvedValueOnce({
        answer_markdown: '- First response',
        citations: [],
        result_count: 1,
        history: [
          { role: 'user', content: 'First question' },
          { role: 'assistant', content: '- First response' },
        ],
      })
      .mockResolvedValueOnce({
        answer_markdown: '- Follow-up response',
        citations: [],
        result_count: 1,
        history: [
          { role: 'user', content: 'First question' },
          { role: 'assistant', content: '- First response' },
          { role: 'user', content: 'Follow-up question' },
          { role: 'assistant', content: '- Follow-up response' },
        ],
      })
      .mockResolvedValueOnce({
        answer_markdown: '- Fresh thread response',
        citations: [],
        result_count: 1,
        history: [
          { role: 'user', content: 'New thread question' },
          { role: 'assistant', content: '- Fresh thread response' },
        ],
      })

    render(<ChatPage />)

    fireEvent.change(screen.getByLabelText('Radio channel'), {
      target: { value: 'Main Dispatch' },
    })
    fireEvent.change(screen.getByLabelText('Ask a question'), {
      target: { value: 'First question' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(mockedRequestChatSummary).toHaveBeenCalledTimes(1)
    })
    expect(mockedRequestChatSummary.mock.calls[0][0].history).toEqual([])

    fireEvent.change(screen.getByLabelText('Ask a question'), {
      target: { value: 'Follow-up question' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(mockedRequestChatSummary).toHaveBeenCalledTimes(2)
    })
    expect(mockedRequestChatSummary.mock.calls[1][0].history.length).toBe(2)

    fireEvent.change(screen.getByLabelText('Radio channel'), {
      target: { value: 'Citywide' },
    })
    fireEvent.change(screen.getByLabelText('Ask a question'), {
      target: { value: 'New thread question' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(mockedRequestChatSummary).toHaveBeenCalledTimes(3)
    })
    expect(mockedRequestChatSummary.mock.calls[2][0].history).toEqual([])
  })

  it('renders citations and request errors', async () => {
    mockedRequestChatSummary.mockResolvedValueOnce({
      answer_markdown: '- Incident digest',
      citations: [
        {
          id: '123',
          start_time: '2026-02-06T10:00:00+00:00',
          talkgroup_description: 'Main Dispatch',
          search_url: 'https://example.com/search#hit-123',
        },
      ],
      result_count: 1,
      history: [
        { role: 'user', content: 'Summarize incidents' },
        { role: 'assistant', content: '- Incident digest' },
      ],
    })

    render(<ChatPage />)

    fireEvent.change(screen.getByLabelText('Radio channel'), {
      target: { value: 'Main Dispatch' },
    })
    fireEvent.change(screen.getByLabelText('Ask a question'), {
      target: { value: 'Summarize incidents' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(screen.getByText(/Incident digest/)).toBeTruthy()
    })
    const citationLink = screen.getByRole('link', { name: /Main Dispatch/ })
    expect(citationLink.getAttribute('href')).toContain('hit-123')

    mockedRequestChatSummary.mockRejectedValueOnce(new Error('boom'))
    fireEvent.change(screen.getByLabelText('Ask a question'), {
      target: { value: 'Try again' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(screen.getByText('boom')).toBeTruthy()
    })
  })
})
