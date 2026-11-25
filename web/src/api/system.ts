import { request } from './client'

export type ServiceStatus =
  | 'starting'
  | 'running'
  | 'unhealthy'
  | 'restarting'
  | 'stopped'
  | 'offline'
  | 'external'

export const STATUS_LABELS: Record<ServiceStatus, string> = {
  starting: '启动中',
  running: '运行中',
  unhealthy: '无响应',
  restarting: '重启中',
  stopped: '已停止',
  offline: '断线',
  external: '自行管理',
}

export interface ServiceState {
  key: string
  name: string
  status: ServiceStatus
  pid: number | null
  restarts: number | null
  last_ok: string | null
  message: string
}

export interface LogicHealth {
  service: string
  ok: boolean
  version: string
  rules_version: number | null
  extra: { databases?: Record<string, boolean> }
}

export interface SystemHealth {
  api: boolean
  logic: LogicHealth | null
}

export const fetchServices = () => request<ServiceState[]>('/api/v1/system/services')
export const fetchHealth = () => request<SystemHealth>('/api/v1/system/health')
