import { createFileRoute } from '@tanstack/react-router'
import Container from 'react-bootstrap/Container'
import LiveFeed from '../components/LiveFeed'

export const Route = createFileRoute('/live')({
  component: LivePage,
})

function LivePage() {
  return (
    <Container fluid={true}>
      <LiveFeed />
    </Container>
  )
}