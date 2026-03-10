'use client'

import {
  ThreadsProvider,
  useCopilotAdditionalInstructions,
  useFrontendTool,
} from '@copilotkit/react-core'
import { CopilotChat } from '@copilotkit/react-ui'
import { useEffect, useMemo, useState } from 'react'
import { Badge, Card, Form, Row, Col } from 'react-bootstrap'
import {
  buildScannerChatInstructions,
  buildScannerSearchUrl,
  createScannerChatThreadId,
  toLocalDateTimeValue,
  type ScannerChatContext,
} from '@/lib/searchState'
import { fetchTalkgroups } from '@/lib/talkgroupsApi'

function ScannerChatTools({ context }: { context: ScannerChatContext }) {
  const contextKey = JSON.stringify(context)

  useCopilotAdditionalInstructions(
    {
      instructions: buildScannerChatInstructions(context),
    },
    [contextKey],
  )

  useFrontendTool(
    {
      name: 'open_search_results',
      description:
        'Open the main transcript search page with a query and optional talkgroup, radio system, and time filters.',
      parameters: [
        {
          name: 'query',
          type: 'string',
          description: 'Optional search query to run in the main transcript search UI.',
          required: false,
        },
        {
          name: 'talkgroupDescription',
          type: 'string',
          description:
            'Optional talkgroup description to filter on. Defaults to the current chat scope.',
          required: false,
        },
        {
          name: 'radioSystem',
          type: 'string',
          description:
            'Optional radio system short name to filter on. Defaults to the current chat scope.',
          required: false,
        },
        {
          name: 'startDatetime',
          type: 'string',
          description:
            'Optional ISO datetime for the start of the search window. Defaults to the current chat scope.',
          required: false,
        },
        {
          name: 'endDatetime',
          type: 'string',
          description:
            'Optional ISO datetime for the end of the search window. Defaults to the current chat scope.',
          required: false,
        },
      ],
      handler: (args) => {
        const url = buildScannerSearchUrl({
          query: typeof args.query === 'string' ? args.query : undefined,
          talkgroupDescription:
            typeof args.talkgroupDescription === 'string'
              ? args.talkgroupDescription
              : context.talkgroupDescription,
          radioSystem:
            typeof args.radioSystem === 'string'
              ? args.radioSystem
              : context.radioSystem,
          startDatetime:
            typeof args.startDatetime === 'string'
              ? args.startDatetime
              : context.startDatetime,
          endDatetime:
            typeof args.endDatetime === 'string'
              ? args.endDatetime
              : context.endDatetime,
        })

        window.location.assign(url)
        return { opened: url }
      },
    },
    [contextKey],
  )

  useFrontendTool(
    {
      name: 'open_call_in_search',
      description:
        'Open the main transcript search page focused on a specific cited call and highlight that result.',
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
          description: 'The cited call start time as epoch seconds.',
          required: true,
        },
        {
          name: 'talkgroupDescription',
          type: 'string',
          description: 'The talkgroup description that contains the cited call.',
          required: true,
        },
        {
          name: 'radioSystem',
          type: 'string',
          description: 'Optional radio system short name for the cited call.',
          required: false,
        },
      ],
      handler: (args) => {
        const url = buildScannerSearchUrl({
          callId: String(args.callId),
          callStartTime:
            typeof args.callStartTime === 'number'
              ? args.callStartTime
              : Number(args.callStartTime),
          talkgroupDescription: String(args.talkgroupDescription),
          radioSystem:
            typeof args.radioSystem === 'string'
              ? args.radioSystem
              : context.radioSystem,
        })

        window.location.assign(url)
        return { opened: url }
      },
    },
    [contextKey],
  )

  return null
}

function buildSuggestionMessage(
  context: ScannerChatContext,
  prompt: string,
): string {
  const scope = context.talkgroupDescription.trim()
    ? ` for ${context.talkgroupDescription.trim()}`
    : ''
  return `${prompt}${scope} between ${context.startDatetime} and ${context.endDatetime}.`
}

export default function ChatPage() {
  const now = useMemo(() => new Date(), [])
  const [talkgroupDescription, setTalkgroupDescription] = useState('')
  const [radioSystem, setRadioSystem] = useState('')
  const [startDatetime, setStartDatetime] = useState(
    toLocalDateTimeValue(new Date(now.getTime() - 2 * 60 * 60 * 1000)),
  )
  const [endDatetime, setEndDatetime] = useState(toLocalDateTimeValue(now))
  const [talkgroupSuggestions, setTalkgroupSuggestions] = useState<string[]>([])
  const [radioSystemSuggestions, setRadioSystemSuggestions] = useState<string[]>([])

  useEffect(() => {
    let isMounted = true

    fetchTalkgroups()
      .then((talkgroups) => {
        if (!isMounted) {
          return
        }

        const nextTalkgroupSuggestions = Array.from(
          new Set(
            talkgroups
              .map((talkgroup) => talkgroup.talkgroup_description?.trim())
              .filter((value): value is string => Boolean(value)),
          ),
        ).sort((left, right) => left.localeCompare(right))

        const nextRadioSystemSuggestions = Array.from(
          new Set(
            talkgroups
              .map((talkgroup) => talkgroup.short_name?.trim())
              .filter((value): value is string => Boolean(value)),
          ),
        ).sort((left, right) => left.localeCompare(right))

        setTalkgroupSuggestions(nextTalkgroupSuggestions)
        setRadioSystemSuggestions(nextRadioSystemSuggestions)
      })
      .catch(() => {
        if (!isMounted) {
          return
        }

        setTalkgroupSuggestions([])
        setRadioSystemSuggestions([])
      })

    return () => {
      isMounted = false
    }
  }, [])

  const context = useMemo<ScannerChatContext>(
    () => ({
      talkgroupDescription: talkgroupDescription.trim(),
      radioSystem: radioSystem.trim(),
      startDatetime,
      endDatetime,
    }),
    [endDatetime, radioSystem, startDatetime, talkgroupDescription],
  )

  const threadId = useMemo(
    () => createScannerChatThreadId(context),
    [context],
  )

  const suggestions = useMemo(
    () => [
      {
        title: 'Incident Summary',
        message: buildSuggestionMessage(
          context,
          'Summarize the most significant incidents',
        ),
      },
      {
        title: 'Unit Activity',
        message: buildSuggestionMessage(
          context,
          'Which units or radio IDs were most active',
        ),
      },
      {
        title: 'Timeline',
        message: buildSuggestionMessage(
          context,
          'Build a concise timeline of the main events',
        ),
      },
    ],
    [context],
  )

  return (
    <div className="chat-page">
      <div className="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3 mb-3">
        <div>
          <h1 className="mb-1">Scanner Chat</h1>
          <p className="text-muted mb-0">
            Investigate transcript activity here, then jump into the main search UI when
            you need the raw results.
          </p>
        </div>

        <Badge bg="light" text="dark" className="align-self-start border">
          Thread {threadId.slice(-8)}
        </Badge>
      </div>

      <Card className="mb-3">
        <Card.Body>
          <Row className="g-3">
            <Col lg={4}>
              <Form.Label htmlFor="chat-talkgroup-description">
                Talkgroup / channel
              </Form.Label>
              <Form.Control
                id="chat-talkgroup-description"
                list="chat-talkgroup-suggestions"
                value={talkgroupDescription}
                onChange={(event) => setTalkgroupDescription(event.target.value)}
                placeholder="e.g. Main Dispatch"
              />
              <datalist id="chat-talkgroup-suggestions">
                {talkgroupSuggestions.map((suggestion) => (
                  <option key={suggestion} value={suggestion} />
                ))}
              </datalist>
            </Col>

            <Col lg={2}>
              <Form.Label htmlFor="chat-radio-system">Radio system</Form.Label>
              <Form.Control
                id="chat-radio-system"
                list="chat-radio-system-suggestions"
                value={radioSystem}
                onChange={(event) => setRadioSystem(event.target.value)}
                placeholder="optional"
              />
              <datalist id="chat-radio-system-suggestions">
                {radioSystemSuggestions.map((suggestion) => (
                  <option key={suggestion} value={suggestion} />
                ))}
              </datalist>
            </Col>

            <Col lg={3}>
              <Form.Label htmlFor="chat-start-datetime">Start time</Form.Label>
              <Form.Control
                id="chat-start-datetime"
                type="datetime-local"
                value={startDatetime}
                onChange={(event) => setStartDatetime(event.target.value)}
              />
            </Col>

            <Col lg={3}>
              <Form.Label htmlFor="chat-end-datetime">End time</Form.Label>
              <Form.Control
                id="chat-end-datetime"
                type="datetime-local"
                value={endDatetime}
                onChange={(event) => setEndDatetime(event.target.value)}
              />
            </Col>
          </Row>

          <p className="text-muted small mb-0 mt-3">
            Changing the scope starts a fresh chat thread so the agent does not mix
            answers across different time windows or channels.
          </p>
        </Card.Body>
      </Card>

      <ThreadsProvider threadId={threadId}>
        <ScannerChatTools context={context} />
        <Card>
          <Card.Body>
            {!context.talkgroupDescription ? (
              <div className="alert alert-warning mb-3">
                No talkgroup is selected. The agent will ask for one before running a
                narrow transcript search unless you explicitly request an all-talkgroups
                scan.
              </div>
            ) : null}

            <CopilotChat
              key={threadId}
              className="scanner-copilot-chat"
              suggestions={suggestions}
              labels={{
                initial: 'Ask about incidents, units, timelines, or patterns in this scope.',
                placeholder: 'Ask a question about the selected transcript window...',
                title: 'Scanner Chat',
              }}
            />
          </Card.Body>
        </Card>
      </ThreadsProvider>
    </div>
  )
}
