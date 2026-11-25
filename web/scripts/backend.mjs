import { fileURLToPath } from 'node:url'
import { loadEnv } from 'vite'

const servers = fileURLToPath(new URL('../../servers/', import.meta.url))

export function apiOrigin(mode = 'development') {
  const env = loadEnv(mode, servers, ['AVALON_API_HOST', 'AVALON_API_PORT'])
  const port = Number(env.AVALON_API_PORT || 7900)
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('servers/.env 中的 AVALON_API_PORT 必须是 1 到 65535 的整数')
  }
  let host = (env.AVALON_API_HOST || '127.0.0.1').trim()
  if (['0.0.0.0', '::', '[::]'].includes(host)) host = '127.0.0.1'
  if (host.includes(':') && !host.startsWith('[')) host = `[${host}]`
  return `http://${host}:${port}`
}
