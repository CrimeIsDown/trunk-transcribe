import { defineEventHandler } from 'h3'
import { copilotRuntimeHandler } from '../../../lib/copilotRuntime'

export default defineEventHandler((event) => {
  return copilotRuntimeHandler(event.request)
})
