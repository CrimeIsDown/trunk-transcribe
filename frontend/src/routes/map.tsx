import { createFileRoute } from '@tanstack/react-router'
import Container from 'react-bootstrap/Container'

import TranscriptMap from '../components/TranscriptMap'

export const Route = createFileRoute('/map')({
  component: MapPage,
})

function MapPage() {
  return (
    <Container fluid={true}>
      <TranscriptMap />
    </Container>
  )
}
