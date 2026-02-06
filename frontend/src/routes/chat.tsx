import { createFileRoute } from '@tanstack/react-router'
import Container from 'react-bootstrap/Container'

import ChatPage from '@/components/chat/ChatPage'

export const Route = createFileRoute('/chat')({
  component: ChatRoute,
})

function ChatRoute() {
  return (
    <Container fluid={true}>
      <ChatPage />
    </Container>
  )
}
