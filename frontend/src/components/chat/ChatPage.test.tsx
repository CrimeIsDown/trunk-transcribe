// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ChatPage from './ChatPage'
import { fetchTalkgroups } from '@/lib/talkgroupsApi'

vi.mock('@copilotkit/react-core', () => ({
  ThreadsProvider: ({ children }: { children: ReactNode }) => children,
  useCopilotAdditionalInstructions: vi.fn(),
  useFrontendTool: vi.fn(),
}))

vi.mock('@copilotkit/react-ui', () => ({
  CopilotChat: () => <div data-testid="copilot-chat">copilot-chat</div>,
}))

vi.mock('@/lib/talkgroupsApi', () => ({
  fetchTalkgroups: vi.fn(),
}))

const mockedFetchTalkgroups = vi.mocked(fetchTalkgroups)

describe('ChatPage', () => {
  beforeEach(() => {
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

  it('prefills a default last-two-hours window and renders the chat shell', async () => {
    render(<ChatPage />)

    const startInput = screen.getByLabelText('Start time') as HTMLInputElement
    const endInput = screen.getByLabelText('End time') as HTMLInputElement
    expect(startInput.value.length).toBeGreaterThan(0)
    expect(endInput.value.length).toBeGreaterThan(0)
    expect(screen.getByTestId('copilot-chat')).toBeTruthy()

    const start = new Date(startInput.value)
    const end = new Date(endInput.value)
    const diffMinutes = (end.getTime() - start.getTime()) / (60 * 1000)
    expect(diffMinutes).toBeGreaterThanOrEqual(119)
    expect(diffMinutes).toBeLessThanOrEqual(121)

    await waitFor(() => {
      expect(mockedFetchTalkgroups).toHaveBeenCalledTimes(1)
    })
  })

  it('loads unique talkgroup suggestions for autocomplete', async () => {
    render(<ChatPage />)

    await waitFor(() => {
      const options = document.querySelectorAll('#chat-talkgroup-suggestions option')
      expect(options.length).toBe(2)
    })
  })
})
