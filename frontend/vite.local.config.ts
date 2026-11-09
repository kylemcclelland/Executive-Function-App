import { defineConfig, mergeConfig } from 'vitest/config'
import base from './vite.config'

export default mergeConfig(
  base,
  defineConfig({ server: { proxy: { '/api': 'http://127.0.0.1:8001' } } }),
)
