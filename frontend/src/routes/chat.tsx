import { createFileRoute } from '@tanstack/react-router'
import { useEffect } from 'react'
import Container from 'react-bootstrap/Container'

export const Route = createFileRoute('/chat')({
  component: ChatRoute,
})

function ChatRoute() {
  const chatUiUrl = import.meta.env.VITE_CHAT_UI_URL || 'http://localhost:7932'

  useEffect(() => {
    window.location.assign(chatUiUrl)
  }, [chatUiUrl])

  return (
    <Container fluid={true}>
      <p className="mt-3">
        Opening scanner chat UI... If you are not redirected, open{' '}
        <a href={chatUiUrl}>{chatUiUrl}</a>.
      </p>
    </Container>
  )
}
