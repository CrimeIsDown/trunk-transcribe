'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  type ChatCitation,
  type ChatHistoryMessage,
  requestChatSummary,
} from '@/lib/chatApi'
import { fetchTalkgroups } from '@/lib/talkgroupsApi'
import { ChatComposer } from './ChatComposer'
import { ChatMessage } from './ChatMessage'

interface UiMessage extends ChatHistoryMessage {
  citations?: ChatCitation[]
  resultCount?: number
}

interface ThreadConfig {
  radio_channel: string
  start_datetime: string
  end_datetime: string
  radio_system?: string
}

function pad2(value: number): string {
  return value.toString().padStart(2, '0')
}

function toLocalDateTimeValue(value: Date): string {
  return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}T${pad2(
    value.getHours(),
  )}:${pad2(value.getMinutes())}`
}

function toThreadSignature(config: ThreadConfig): string {
  return JSON.stringify(config)
}

export default function ChatPage() {
  const now = useMemo(() => new Date(), [])
  const [radioChannel, setRadioChannel] = useState('')
  const [radioSystem, setRadioSystem] = useState('')
  const [startDatetime, setStartDatetime] = useState(
    toLocalDateTimeValue(new Date(now.getTime() - 2 * 60 * 60 * 1000)),
  )
  const [endDatetime, setEndDatetime] = useState(toLocalDateTimeValue(now))
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [history, setHistory] = useState<ChatHistoryMessage[]>([])
  const [threadSignature, setThreadSignature] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [channelSuggestions, setChannelSuggestions] = useState<string[]>([])

  useEffect(() => {
    let isMounted = true
    fetchTalkgroups()
      .then((talkgroups) => {
        if (!isMounted) {
          return
        }
        const channels = Array.from(
          new Set(
            talkgroups
              .map((talkgroup) => talkgroup.talkgroup_description?.trim())
              .filter((value): value is string => Boolean(value)),
          ),
        ).sort((a, b) => a.localeCompare(b))
        setChannelSuggestions(channels)
      })
      .catch(() => {
        if (isMounted) {
          setChannelSuggestions([])
        }
      })

    return () => {
      isMounted = false
    }
  }, [])

  const submitQuestion = async () => {
    const trimmedQuestion = question.trim()
    const trimmedChannel = radioChannel.trim()
    if (!trimmedQuestion) {
      setError('Question is required.')
      return
    }
    if (!trimmedChannel) {
      setError('Radio channel is required.')
      return
    }

    const startDate = new Date(startDatetime)
    const endDate = new Date(endDatetime)
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
      setError('Valid start and end datetimes are required.')
      return
    }
    if (startDate >= endDate) {
      setError('Start datetime must be before end datetime.')
      return
    }

    const config: ThreadConfig = {
      radio_channel: trimmedChannel,
      start_datetime: startDate.toISOString(),
      end_datetime: endDate.toISOString(),
      radio_system: radioSystem.trim() || undefined,
    }
    const currentSignature = toThreadSignature(config)
    const shouldReset =
      messages.length > 0 &&
      threadSignature !== null &&
      currentSignature !== threadSignature

    const baseMessages = shouldReset ? [] : messages
    const requestHistory = shouldReset ? [] : history
    const userMessage: UiMessage = { role: 'user', content: trimmedQuestion }

    setError('')
    setIsLoading(true)
    setMessages([...baseMessages, userMessage])

    try {
      const response = await requestChatSummary({
        radio_channel: config.radio_channel,
        start_datetime: config.start_datetime,
        end_datetime: config.end_datetime,
        question: trimmedQuestion,
        history: requestHistory,
        radio_system: config.radio_system,
      })

      const assistantMessage: UiMessage = {
        role: 'assistant',
        content: response.answer_markdown,
        citations: response.citations,
        resultCount: response.result_count,
      }

      setMessages([...baseMessages, userMessage, assistantMessage])
      setHistory(response.history)
      setThreadSignature(currentSignature)
      setQuestion('')
    } catch (requestError) {
      setMessages(baseMessages)
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Failed to generate summary.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="chat-page">
      <h1 className="mb-3">Scanner Summary Chat</h1>

      <div className="card mb-3">
        <div className="card-body">
          <div className="row g-3">
            <div className="col-lg-4">
              <label htmlFor="radio-channel" className="form-label">
                Radio channel
              </label>
              <input
                id="radio-channel"
                list="channel-suggestions"
                className="form-control"
                value={radioChannel}
                onChange={(event) => setRadioChannel(event.target.value)}
                placeholder="e.g. Main Dispatch"
              />
              <datalist id="channel-suggestions">
                {channelSuggestions.map((channel) => (
                  <option key={channel} value={channel} />
                ))}
              </datalist>
            </div>
            <div className="col-lg-2">
              <label htmlFor="radio-system" className="form-label">
                Radio system
              </label>
              <input
                id="radio-system"
                className="form-control"
                value={radioSystem}
                onChange={(event) => setRadioSystem(event.target.value)}
                placeholder="optional"
              />
            </div>
            <div className="col-lg-3">
              <label htmlFor="summary-start" className="form-label">
                Start time
              </label>
              <input
                id="summary-start"
                type="datetime-local"
                className="form-control"
                value={startDatetime}
                onChange={(event) => setStartDatetime(event.target.value)}
              />
            </div>
            <div className="col-lg-3">
              <label htmlFor="summary-end" className="form-label">
                End time
              </label>
              <input
                id="summary-end"
                type="datetime-local"
                className="form-control"
                value={endDatetime}
                onChange={(event) => setEndDatetime(event.target.value)}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-body chat-container">
          {messages.length === 0 ? (
            <p className="text-muted mb-3">
              Ask for an incident digest in the selected time window.
            </p>
          ) : null}

          {messages.map((message, index) => (
            <ChatMessage
              key={`${message.role}-${index}`}
              role={message.role}
              content={message.content}
              citations={message.citations}
              resultCount={message.resultCount}
            />
          ))}

          {error ? <div className="alert alert-danger mt-3 mb-0">{error}</div> : null}

          <div className="mt-3">
            <ChatComposer
              question={question}
              disabled={isLoading}
              onQuestionChange={setQuestion}
              onSubmit={submitQuestion}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
