'use client'

import {
  ThreadsProvider,
  useCopilotAdditionalInstructions,
  useFrontendTool,
} from '@copilotkit/react-core'
import { CopilotChat } from '@copilotkit/react-ui'
import { useMemo } from 'react'
import { Badge, Card } from 'react-bootstrap'
import { useInstantSearch } from 'react-instantsearch'
import type { UiState } from 'instantsearch.js'

import {
  DEFAULT_MAX_ANALYSIS_HITS,
  buildScannerChatInstructions,
  buildScannerSearchUrl,
  createScannerChatThreadId,
  describeScannerSearchScope,
  extractScannerSearchScope,
  isBroadScannerSearchScope,
  type ScannerSearchScope,
} from '@/lib/searchState'

function SearchAnalysisTools({
  indexName,
  scope,
}: {
  indexName: string
  scope: ScannerSearchScope
}) {
  const scopeKey = JSON.stringify(scope)

  useCopilotAdditionalInstructions(
    {
      instructions: buildScannerChatInstructions(scope),
    },
    [scopeKey],
  )

  useFrontendTool(
    {
      name: 'get_current_search_scope',
      description:
        'Return the exact active transcript search scope from the current search page, including the query, refinements, hierarchy, and time range.',
      parameters: [],
      handler: () => ({
        scope,
      }),
    },
    [scopeKey],
  )

  useFrontendTool(
    {
      name: 'open_search_results',
      description:
        'Open the transcript search page with the exact current search scope applied.',
      parameters: [],
      handler: () => {
        const url = buildScannerSearchUrl({
          scope,
          indexName,
        })

        window.location.assign(url)
        return { opened: url }
      },
    },
    [indexName, scopeKey],
  )

  useFrontendTool(
    {
      name: 'open_call_in_search',
      description:
        'Open the transcript search page focused on a cited call while preserving the current refinements.',
      parameters: [
        {
          name: 'callId',
          type: 'string',
          description: 'The call identifier to highlight in the search results.',
          required: true,
        },
        {
          name: 'callStartTime',
          type: 'number',
          description:
            'Optional cited call start time as epoch seconds. Used to focus the search if no explicit time range is active.',
          required: false,
        },
      ],
      handler: (args) => {
        const url = buildScannerSearchUrl({
          scope,
          indexName,
          callId: String(args.callId),
          callStartTime:
            typeof args.callStartTime === 'number'
              ? args.callStartTime
              : undefined,
        })

        window.location.assign(url)
        return { opened: url }
      },
    },
    [indexName, scopeKey],
  )

  return null
}

function buildSuggestionMessage(
  scope: ScannerSearchScope,
  prompt: string,
): string {
  if (scope.query) {
    return `${prompt} for the current search query "${scope.query}".`
  }

  return `${prompt} using the current transcript search filters.`
}

export default function SearchAnalysisPanel({
  indexName,
}: {
  indexName: string
}) {
  const { indexUiState, results } = useInstantSearch<UiState>()

  const scope = useMemo(
    () =>
      extractScannerSearchScope(
        (indexUiState || {}) as Record<string, unknown>,
        DEFAULT_MAX_ANALYSIS_HITS,
      ),
    [indexUiState],
  )

  const threadId = useMemo(() => createScannerChatThreadId(scope), [scope])
  const scopeSummary = useMemo(() => describeScannerSearchScope(scope), [scope])
  const isBroadScope = useMemo(() => isBroadScannerSearchScope(scope), [scope])

  const suggestions = useMemo(
    () => [
      {
        title: 'Incident Summary',
        message: buildSuggestionMessage(
          scope,
          'Summarize the most important incidents in these search results',
        ),
      },
      {
        title: 'Timeline',
        message: buildSuggestionMessage(
          scope,
          'Build a concise timeline of the key events in these search results',
        ),
      },
      {
        title: 'Patterns',
        message: buildSuggestionMessage(
          scope,
          'Identify recurring units, locations, or patterns in these search results',
        ),
      },
    ],
    [scope],
  )

  return (
    <Card className="mb-3 search-analysis-panel">
      <Card.Body>
        <div className="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3 mb-3">
          <div>
            <h2 className="fs-4 mb-1">AI Analysis</h2>
            <p className="text-muted mb-0">
              Chat about the current search results. The agent uses the active query,
              filters, hierarchy selection, and time window, and it inspects up to{' '}
              {scope.maxHits || DEFAULT_MAX_ANALYSIS_HITS} matching calls.
            </p>
          </div>

          <Badge bg="light" text="dark" className="align-self-start border">
            Thread {threadId.slice(-8)}
          </Badge>
        </div>

        {scopeSummary.length > 0 ? (
          <div className="mb-3">
            {scopeSummary.map((item) => (
              <Badge
                bg="light"
                text="dark"
                className="me-2 mb-2 border search-analysis-badge"
                key={item}
              >
                {item}
              </Badge>
            ))}
          </div>
        ) : null}

        {isBroadScope ? (
          <div className="alert alert-warning mb-3">
            No query or filters are active yet. Add a search term, time range, or
            refinement before asking for narrow analysis.
          </div>
        ) : null}

        {results?.nbHits > (scope.maxHits || DEFAULT_MAX_ANALYSIS_HITS) ? (
          <div className="alert alert-secondary mb-3">
            The current search matches {results.nbHits.toLocaleString()} calls. AI
            analysis will review the newest{' '}
            {(scope.maxHits || DEFAULT_MAX_ANALYSIS_HITS).toLocaleString()} matches.
          </div>
        ) : null}

        <ThreadsProvider threadId={threadId}>
          <SearchAnalysisTools indexName={indexName} scope={scope} />
          <CopilotChat
            key={threadId}
            className="scanner-copilot-chat"
            suggestions={suggestions}
            labels={{
              initial:
                'Ask about the current search results, such as incidents, timelines, units, or patterns.',
              placeholder: 'Ask a question about the current search results...',
              title: 'Transcript Analysis',
            }}
          />
        </ThreadsProvider>
      </Card.Body>
    </Card>
  )
}
