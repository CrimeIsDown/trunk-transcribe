import { createFileRoute } from '@tanstack/react-router'
import Container from 'react-bootstrap/Container'
import Search from '../components/Search'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  return (
    <Container fluid={true}>
      <Search />
    </Container>
  )
}
