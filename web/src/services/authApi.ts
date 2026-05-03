import request from './api'
import type { User } from '../stores/useAuthStore'

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface UserListResponse {
  total: number
  page: number
  page_size: number
  items: User[]
}

export function login(data: LoginRequest) {
  return request<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function register(data: RegisterRequest) {
  return request<User>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function logout() {
  return request<{ message: string }>('/auth/logout', {
    method: 'POST',
  })
}

export function getMe() {
  return request<User>('/auth/me')
}

export function getUsers(params: {
  page?: number
  page_size?: number
  role?: string
  is_active?: boolean
  search?: string
}) {
  const query = new URLSearchParams()
  if (params.page) query.set('page', params.page.toString())
  if (params.page_size) query.set('page_size', params.page_size.toString())
  if (params.role) query.set('role', params.role)
  if (params.is_active !== undefined) query.set('is_active', params.is_active.toString())
  if (params.search) query.set('search', params.search)
  return request<UserListResponse>(`/users?${query.toString()}`)
}

export function updateUserRole(userId: number, role: string) {
  return request<User>(`/users/${userId}/role`, {
    method: 'PUT',
    body: JSON.stringify({ role }),
  })
}

export function updateUserStatus(userId: number, isActive: boolean) {
  return request<User>(`/users/${userId}/status`, {
    method: 'PUT',
    body: JSON.stringify({ is_active: isActive }),
  })
}

export function resetUserPassword(userId: number) {
  return request<{ success: boolean; message: string }>(`/users/${userId}/reset-password`, {
    method: 'POST',
  })
}
