import React from 'react';

import Container from 'react-bootstrap/Container';

import Search from './Search';

export default function Page() {
  return (
    <Container fluid={true}>
      <Search />
    </Container>
  );
}
