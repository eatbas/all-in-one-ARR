import path from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:3223',
      '/webhook': 'http://localhost:3223',
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    clearMocks: true,
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      // main.tsx is the DOM bootstrap (the analogue of the backend's excluded
      // `if __name__ == "__main__"` block); test scaffolding is not product code.
      exclude: [
        'src/main.tsx',
        'src/test/**',
        'src/**/*.test.{ts,tsx}',
        'src/**/*.d.ts',
      ],
      thresholds: {
        // Shorthand: statements, branches, functions, and lines must all be 100%.
        100: true,
      },
    },
  },
})
