import { create } from 'zustand'
import type { QueryResult, SystemStatus, PageListItem } from '../types'

function getInitialTheme(): 'light' | 'dark' {
  const stored = localStorage.getItem('theme')
  if (stored === 'dark' || stored === 'light') return stored
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark'
  return 'light'
}

function applyTheme(theme: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem('theme', theme)
}

const initialTheme = getInitialTheme()
applyTheme(initialTheme)

interface AppState {
  theme: 'light' | 'dark'
  toggleTheme: () => void

  currentQuery: string
  queryResult: QueryResult | null
  queryLoading: boolean
  setQuery: (query: string) => void
  setQueryResult: (result: QueryResult | null) => void
  setQueryLoading: (loading: boolean) => void

  systemStatus: SystemStatus | null
  setSystemStatus: (status: SystemStatus | null) => void

  knowledgeList: PageListItem[]
  setKnowledgeList: (list: PageListItem[]) => void
}

export const useAppStore = create<AppState>((set) => ({
  theme: initialTheme,
  toggleTheme: () => set((state) => {
    const newTheme = state.theme === 'light' ? 'dark' : 'light'
    applyTheme(newTheme)
    return { theme: newTheme }
  }),

  currentQuery: '',
  queryResult: null,
  queryLoading: false,
  setQuery: (query) => set({ currentQuery: query }),
  setQueryResult: (result) => set({ queryResult: result }),
  setQueryLoading: (loading) => set({ queryLoading: loading }),

  systemStatus: null,
  setSystemStatus: (status) => set({ systemStatus: status }),

  knowledgeList: [],
  setKnowledgeList: (list) => set({ knowledgeList: list }),
}))
