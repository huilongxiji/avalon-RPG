import { request } from './client'

export type Role = 'viewer' | 'editor' | 'admin' | 'super'
export const ROLE_LABELS: Record<Role, string> = { viewer: '访客', editor: '编辑者', admin: '管理员', super: '超级管理员' }
export const ROLE_HELP: Record<Role, string> = {
  viewer: '查看网站数据', editor: '查看数据、修改和校验规则草稿',
  admin: '编辑草稿、发布和回滚规则', super: '管理规则及网站账号',
}
export interface WebUser {
  id: number
  username: string
  role: Role
  disabled: boolean
  created_at: string
  last_login_at: string | null
}
export interface Identity { user: WebUser; csrf_token: string }
export interface UserPage { items: WebUser[]; total: number; page: number; size: number }
const json = (body: unknown) => ({ body: JSON.stringify(body) })
export const fetchIdentity = () => request<Identity>('/api/v1/auth/me')
export const login = (username: string, password: string) =>
  request<Identity>('/api/v1/auth/login', { method: 'POST', ...json({ username, password }) })
export const logout = () => request<null>('/api/v1/auth/logout', { method: 'POST' })
export const changePassword = (current_password: string, password: string) =>
  request<null>('/api/v1/auth/password', { method: 'PUT', ...json({ current_password, password }) })
export const fetchUsers = (params: URLSearchParams) => request<UserPage>(`/api/v1/admin/users?${params}`)
export const updateUser = (id: number, role: Role, disabled: boolean) =>
  request<WebUser>(`/api/v1/admin/users/${id}`, { method: 'PATCH', ...json({ role, disabled }) })
export const resetPassword = (id: number, password: string) =>
  request<null>(`/api/v1/admin/users/${id}/password`, { method: 'PUT', ...json({ password }) })
