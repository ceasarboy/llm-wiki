export interface WikiPage {
  id: string
  title: string
  type: 'entity' | 'concept' | 'paper' | 'summary' | 'synthesis' | 'comparison' | 'faq' | 'exploration'
  status: 'draft' | 'generated' | 'reviewed' | 'stable' | 'rejected' | 'requires_manual_review'
  tags: string[]
  updated: string
  content?: string
  frontmatter?: Record<string, unknown>
}

export interface QueryResult {
  question: string
  answer: string
  sources: SourceRef[]
  relatedQuestions: string[]
  timestamp: string
}

export interface SourceRef {
  id: string
  title: string
  path: string
  relevance: number
}

export interface SystemStatus {
  totalDocs: number
  processedDocs: number
  pendingDocs: number
  passRate: number
  avgScore: number
  reviewQueue: number
  lastCheck: string
}

export interface PageListItem {
  id: string
  title: string
  type: WikiPage['type']
  tags: string[]
  updated: string
  summary?: string
}
