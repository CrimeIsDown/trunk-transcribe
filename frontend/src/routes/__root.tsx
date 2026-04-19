import { CopilotKit } from '@copilotkit/react-core'
import { HeadContent, Scripts, createRootRoute } from '@tanstack/react-router'
import { TanStackRouterDevtoolsPanel } from '@tanstack/react-router-devtools'
import { TanStackDevtools } from '@tanstack/react-devtools'
import type { ReactNode } from 'react'

import Header from '../components/Header'
import { AppProviders } from '../providers/AppProviders'

import appCss from '../styles.css?url'
import copilotCss from '@copilotkit/react-ui/styles.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      {
        charSet: 'utf-8',
      },
      {
        name: 'viewport',
        content: 'width=device-width, initial-scale=1',
      },
      {
        title: 'trunk-transcribe',
      },
      {
        name: 'description',
        content: 'Search transcripts of public safety radio transmissions',
      },
    ],
    links: [
      {
        rel: 'stylesheet',
        href: appCss,
      },
      {
        rel: 'stylesheet',
        href: copilotCss,
      },
    ],
  }),

  notFoundComponent: () => {
    return (
      <div className="container mt-5 text-center">
        <h1>404 - Page Not Found</h1>
        <p>The page you're looking for doesn't exist.</p>
        <a href="/" className="btn btn-primary">Go Home</a>
      </div>
    )
  },

  shellComponent: RootDocument,
})

function RootDocument({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        <CopilotKit
          runtimeUrl="/api/copilotkit"
          agent="scanner_chat"
          showDevConsole={import.meta.env.DEV}
        >
          <AppProviders>
            <Header />
            {children}
            <TanStackDevtools
              config={{
                position: 'bottom-left',
              }}
              plugins={[
                {
                  name: 'Tanstack Router',
                  render: <TanStackRouterDevtoolsPanel />,
                },
              ]}
            />
            <Scripts />
          </AppProviders>
        </CopilotKit>
      </body>
    </html>
  )
}
