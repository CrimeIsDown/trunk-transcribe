import 'bootstrap/dist/css/bootstrap.min.css';
import 'instantsearch.css/themes/satellite-min.css';
import './styles/globals.scss';
import React from 'react';

export const metadata = {
  title: 'trunk-transcribe',
  description: 'Search transcripts of public safety radio transmissions',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
