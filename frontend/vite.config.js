import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  // The production build is served from secotter.org/quiz-app/; the dev server stays at /
  base: command === 'build' ? '/quiz-app/' : '/',
}))
