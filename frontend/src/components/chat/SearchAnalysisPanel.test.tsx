// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SearchAnalysisPanel from './SearchAnalysisPanel'

const mocks = vi.hoisted(() => ({
  useCopilotAdditionalInstructions: vi.fn(),
  useFrontendTool: vi.fn(),
  useInstantSearch: vi.fn(),
}))

vi.mock('@copilotkit/react-core', () => ({
  ThreadsProvider: ({ children }: { children: ReactNode }) => children,
  useCopilotAdditionalInstructions: mocks.useCopilotAdditionalInstructions,
  useFrontendTool: mocks.useFrontendTool,
}))

vi.mock('@copilotkit/react-ui', () => ({
  CopilotChat: () => <div data-testid="copilot-chat">copilot-chat</div>,
}))

vi.mock('react-instantsearch', () => ({
  useInstantSearch: mocks.useInstantSearch,
}))

describe('SearchAnalysisPanel', () => {
  beforeEach(() => {
    mocks.useCopilotAdditionalInstructions.mockReset()
    mocks.useFrontendTool.mockReset()
    mocks.useInstantSearch.mockReset()
  })

  it('renders active search scope and warns when analysis will be truncated', () => {
    mocks.useInstantSearch.mockReturnValue({
      indexUiState: {
        query: 'shots fired',
        refinementList: {
          short_name: ['sys1'],
          talkgroup_tag: ['Zone 10'],
        },
        range: {
          start_time: '1741500000:1741507200',
        },
      },
      results: {
        nbHits: 500,
      },
    })

    render(<SearchAnalysisPanel indexName="calls" />)

    expect(screen.getByText('AI Analysis')).toBeTruthy()
    expect(screen.getByText(/Query: shots fired/)).toBeTruthy()
    expect(screen.getByText(/short_name: sys1/)).toBeTruthy()
    expect(screen.getByText(/talkgroup_tag: Zone 10/)).toBeTruthy()
    expect(screen.getByText(/review the newest 200 matches/i)).toBeTruthy()
    expect(screen.getByTestId('copilot-chat')).toBeTruthy()
    expect(mocks.useFrontendTool).toHaveBeenCalledTimes(3)
  })

  it('flags broad scopes and injects current-scope instructions', () => {
    mocks.useInstantSearch.mockReturnValue({
      indexUiState: {},
      results: {
        nbHits: 0,
      },
    })

    render(<SearchAnalysisPanel indexName="calls" />)

    expect(
      screen.getByText(/No query or filters are active yet/i),
    ).toBeTruthy()
    expect(mocks.useCopilotAdditionalInstructions).toHaveBeenCalledTimes(1)
    expect(
      mocks.useCopilotAdditionalInstructions.mock.calls[0][0].instructions,
    ).toContain('get_current_search_scope')
  })
})
