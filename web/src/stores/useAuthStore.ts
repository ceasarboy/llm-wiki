import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface User {
  id: number
  username: string
  email: string
  role: 'admin' | 'maintainer' | 'core' | 'general'
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

interface AuthState {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  setAuth: (token: string, user: User) => void
  logout: () => void
  updateUser: (user: User) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      setAuth: (token, user) =>
        set({
          token,
          user,
          isAuthenticated: true,
        }),
      logout: () =>
        set({
          token: null,
          user: null,
          isAuthenticated: false,
        }),
      updateUser: (user) =>
        set({
          user,
        }),
    }),
    {
      name: 'auth-storage',
    }
  )
)

export const hasRole = (user: User | null, roles: string[]): boolean => {
  if (!user) return false
  return roles.includes(user.role)
}

export const canEdit = (user: User | null): boolean => {
  return hasRole(user, ['admin', 'core'])
}

export const canViewLogs = (user: User | null): boolean => {
  return hasRole(user, ['admin', 'maintainer'])
}

export const canManageUsers = (user: User | null): boolean => {
  return hasRole(user, ['admin'])
}
