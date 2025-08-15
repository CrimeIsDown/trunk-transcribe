import React from 'react';

import Container from 'react-bootstrap/Container';

import LiveFeed from './LiveFeed';

export default function Page() {
  return (
    <Container fluid={true}>
      <LiveFeed />
    </Container>
  );
}
