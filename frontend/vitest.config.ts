import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tsConfigPaths from 'vite-tsconfig-paths'

export default defineConfig({
  plugins: [
    tsConfigPaths({
      projects: ['./tsconfig.json'],
    }),
    react(),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
