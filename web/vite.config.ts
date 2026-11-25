import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { apiOrigin } from './scripts/backend.mjs'

// 后端地址来自 servers/.env；前端自己的环境文件仍在 web。
// 开发时代理到 API，上线时由 API 托管根 data/web/dist。
export default defineConfig(({ mode }) => {
  const api = apiOrigin(mode)
  return {
    plugins: [vue()],
    envDir: fileURLToPath(new URL('.', import.meta.url)),
    envPrefix: 'AVALON_PUBLIC_', // 不把令牌等配置暴露给浏览器
    cacheDir: fileURLToPath(new URL('../data/cache/vite', import.meta.url)),
    build: {
      outDir: fileURLToPath(new URL('../data/web/dist', import.meta.url)),
      emptyOutDir: true,
    },
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: api, xfwd: true }, // 保留 Host，供登录请求来源校验
        '/ws': { target: api.replace(/^http:/, 'ws:'), ws: true },
      },
    },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true },
  }
})
