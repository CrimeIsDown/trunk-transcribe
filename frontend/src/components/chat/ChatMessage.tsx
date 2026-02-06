import ReactMarkdown from 'react-markdown'
import type { ChatCitation, ChatRole } from '@/lib/chatApi'

interface ChatMessageProps {
  role: ChatRole
  content: string
  citations?: ChatCitation[]
  resultCount?: number
}

export function ChatMessage({
  role,
  content,
  citations = [],
  resultCount,
}: ChatMessageProps) {
  const isAssistant = role === 'assistant'

  return (
    <div className={`chat-message ${isAssistant ? 'assistant' : 'user'}`}>
      <div className="chat-message-role">{isAssistant ? 'Assistant' : 'You'}</div>
      <div className="chat-message-content">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
      {isAssistant && typeof resultCount === 'number' ? (
        <div className="chat-message-meta">Results used: {resultCount}</div>
      ) : null}
      {isAssistant && citations.length > 0 ? (
        <ul className="chat-citations">
          {citations.map((citation) => (
            <li key={`${citation.id}-${citation.start_time}`}>
              {citation.search_url ? (
                <a href={citation.search_url} target="_blank" rel="noopener noreferrer">
                  {citation.talkgroup_description} | {citation.start_time} | #{citation.id}
                </a>
              ) : (
                <span>
                  {citation.talkgroup_description} | {citation.start_time} | #{citation.id}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
