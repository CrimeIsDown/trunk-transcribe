import { defineConfig } from 'vite'
import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import viteReact from '@vitejs/plugin-react'
import tsConfigPaths from 'vite-tsconfig-paths'
import tailwindcss from '@tailwindcss/vite'
import { nitro } from 'nitro/vite'

const config = defineConfig({
  plugins: [
    // this is the plugin that enables path aliases
    tsConfigPaths({
      projects: ['./tsconfig.json'],
    }),
    tailwindcss(),
    nitro(),
    tanstackStart(),
    viteReact(),
  ],
})

export default config
