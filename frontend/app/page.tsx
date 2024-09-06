import React from 'react';

import Container from 'react-bootstrap/Container';

import Search from './Search';

export const dynamic = 'force-dynamic';

export default function Page() {
  return (
    <Container fluid={true}>
      <Search />
    </Container>
  );
}
