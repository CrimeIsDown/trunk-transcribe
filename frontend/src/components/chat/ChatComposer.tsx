interface ChatComposerProps {
  question: string
  disabled?: boolean
  onQuestionChange: (value: string) => void
  onSubmit: () => void
}

export function ChatComposer({
  question,
  disabled = false,
  onQuestionChange,
  onSubmit,
}: ChatComposerProps) {
  return (
    <div className="chat-composer">
      <label htmlFor="chat-question" className="form-label mb-1">
        Ask a question
      </label>
      <textarea
        id="chat-question"
        className="form-control mb-2"
        rows={3}
        value={question}
        disabled={disabled}
        onChange={(event) => onQuestionChange(event.target.value)}
        placeholder="Summarize notable incidents and traffic patterns."
      />
      <div className="d-flex justify-content-end">
        <button
          type="button"
          className="btn btn-primary"
          disabled={disabled || !question.trim()}
          onClick={onSubmit}
        >
          {disabled ? 'Generating...' : 'Send'}
        </button>
      </div>
    </div>
  )
}
