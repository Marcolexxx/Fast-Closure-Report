import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import federation from '@originjs/vite-plugin-federation'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // PRD Layer 3: Module Federation — Shell is Host, Skill UIs are Remotes
    // When a Skill remote is deployed, add it to the remotes map below
    // and import via: const SkillComp = React.lazy(() => import('skill_event_report/UIComponents'))
    federation({
      name: 'aicopilot_shell',
      // Remotes declared here; each Skill publishes its own remote entry
      remotes: {
        // Example: 'skill_event_report': 'http://localhost:5001/assets/remoteEntry.js',
      },
      // Expose shell utilities for Skill UIs to import (optional)
      exposes: {},
      shared: {
        react: { singleton: true, requiredVersion: '^18.0.0' },
        'react-dom': { singleton: true, requiredVersion: '^18.0.0' },
      },
    }),
  ],
  // Module federation requires top-level await support
  build: {
    target: 'esnext',
    minify: false,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})

