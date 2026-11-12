import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base 用相對路徑：同一份打包結果可以放在 GitHub Pages 的子路徑（/tw-stock-terminal/）或任何靜態主機。
// 路由用 hash，所以不需要主機的改寫規則。
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  build: {
    target: 'es2022',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
})
