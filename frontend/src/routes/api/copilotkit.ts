import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/api/copilotkit')({
  component: undefined,
  server: {
    handlers: {
      ANY: async ({ request }) => {
        await import('reflect-metadata')
        const { copilotRuntimeHandler } = await import('../../../server/lib/copilotRuntime')
        return copilotRuntimeHandler(request)
      },
    },
  },
})
