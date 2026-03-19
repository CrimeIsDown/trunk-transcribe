import 'reflect-metadata'
import { HttpAgent } from '@ag-ui/client'
import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNodeHttpEndpoint,
} from '@copilotkit/runtime'

const chatAgentUrl = (process.env.CHAT_AGENT_URL || 'http://localhost:7932').replace(
  /\/$/,
  '',
)

const runtime = new CopilotRuntime({
  agents: {
    scanner_chat: new HttpAgent({
      url: chatAgentUrl,
    }),
  },
})

export const copilotRuntimeHandler = copilotRuntimeNodeHttpEndpoint({
  runtime,
  serviceAdapter: new ExperimentalEmptyAdapter(),
  endpoint: '/api/copilotkit',
})
