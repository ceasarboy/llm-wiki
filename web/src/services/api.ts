const API_BASE = '/api'

let isRedirecting = false

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const authStorage = localStorage.getItem('auth-storage')
  let token: string | null = null
  
  if (authStorage) {
    try {
      const parsed = JSON.parse(authStorage)
      token = parsed.state?.token || null
    } catch {
      // ignore
    }
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  
  if (options?.headers) {
    const optHeaders = options.headers as Record<string, string>
    Object.keys(optHeaders).forEach(key => {
      headers[key] = optHeaders[key]
    })
  }
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })
  if (!res.ok) {
    if (res.status === 401 && !isRedirecting) {
      isRedirecting = true
      localStorage.removeItem('auth-storage')
      window.location.href = '/login'
      setTimeout(() => { isRedirecting = false }, 1000)
      throw new Error('登录已过期，请重新登录')
    }
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `API Error: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

export default request

/** 自然语言查询 */
export function postQuery(question: string) {
  return request<{ answer: string; sources: { id: string; title: string; path: string; relevance: number }[]; related_questions: string[] }>('/query', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

/** 知识库搜索 */
export function searchKnowledge(query: string, type?: string) {
  const params = new URLSearchParams({ q: query })
  if (type) params.set('type', type)
  return request<{ results: { id: string; title: string; type: string; tags: string[]; updated: string; summary?: string }[] }>('/search?' + params)
}

/** 获取页面列表 */
export function getPages(type?: string, page = 1, pageSize = 20) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (type) params.set('type', type)
  return request<{ items: { id: string; title: string; type: string; tags: string[]; updated: string; summary?: string }[]; total: number }>(`/pages?${params}`)
}

/** 获取页面详情 */
export function getPageDetail(id: string) {
  return request<{ id: string; title: string; type: string; status: string; content: string; frontmatter: Record<string, unknown>; tags: string[]; updated: string }>(`/pages/${encodeURIComponent(id)}`)
}

/** 系统状态 */
export function getSystemStatus() {
  return request<{ total_docs: number; processed_docs: number; pending_docs: number; pass_rate: number; avg_score: number; review_queue: number; last_check: string }>('/status')
}

/** 热门查询 */
export function getHotQueries() {
  return request<{ queries: string[] }>('/hot-queries')
}

/** 最近更新 */
export function getRecentUpdates(limit = 5) {
  return request<{ items: { id: string; title: string; type: string; updated: string }[] }>(`/recent-updates?limit=${limit}`)
}

/** 获取原文列表 */
export function getRawDocuments(page = 1, pageSize = 50, search?: string) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (search) params.set('search', search)
  return request<{ items: { id: string; title: string; path: string; size: number; updated: string }[]; total: number }>(`/raw?${params}`)
}

/** 获取原文详情 */
export function getRawDocument(id: string) {
  return request<{ id: string; title: string; path: string; content: string; size: number; updated: string }>(`/raw/${encodeURIComponent(id)}`)
}

/** 获取PDF列表 */
export function getPDFs(page = 1, pageSize = 50, search?: string) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (search) params.set('search', search)
  return request<{ items: { id: string; title: string; path: string; size: number; size_mb: number; updated: string }[]; total: number }>(`/pdfs?${params}`)
}

/** 保存页面内容 */
export function savePage(id: string, content: string) {
  return request<{ success: boolean; message: string }>(`/pages/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

/** 保存原文内容 */
export function saveRawDocument(id: string, content: string, filename?: string) {
  const body: Record<string, string> = { content }
  if (filename) body.filename = filename
  return request<{ success: boolean; message: string; new_id?: string }>(`/raw/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

/** 获取原文对应PDF的URL */
export function getRawPdfUrl(id: string): string {
  return `/api/raw/${encodeURIComponent(id)}/pdf`
}

/** 人工审核请求 */
export interface ManualReviewRequest {
  action: 'approve' | 'reject' | 'request_changes'
  comment?: string
  reviewer?: string
}

/** 人工审核响应 */
export interface ManualReviewResponse {
  success: boolean
  message: string
  new_status: string
}

/** 提交人工审核 */
export function submitManualReview(id: string, data: ManualReviewRequest) {
  return request<ManualReviewResponse>(`/pages/${encodeURIComponent(id)}/manual-review`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** 论文复审 */
export function recheckPage(id: string, reason: string) {
  return request<{ success: boolean; message: string; needsUpdate: boolean }>(`/pages/${encodeURIComponent(id)}/recheck`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

/** 获取页面历史版本列表 */
export function getPageHistory(id: string) {
  return request<{ items: { version: number; filename: string; path: string; saved_at: string; save_reason: string; size: number }[]; total: number }>(`/pages/${encodeURIComponent(id)}/history`)
}

/** 获取历史版本详情 */
export function getHistoryVersion(id: string, version: number) {
  return request<{ version: number; filename: string; content: string; saved_at: string; save_reason: string; frontmatter: Record<string, unknown> }>(`/pages/${encodeURIComponent(id)}/history/${version}`)
}

/** 获取节点邻居子图 */
export function getGraphNeighbors(nodeId: string, depth: number = 1) {
  return request<{ nodes: { id: string; label: string; type: string; tags: string[] }[]; edges: { id: string; source: string; target: string; type: string }[]; metadata: { totalNodes: number; totalEdges: number; centerNode?: string } }>(`/graph/neighbors/${encodeURIComponent(nodeId)}?depth=${depth}`)
}

/** PDF文件信息 */
export interface PDFFile {
  filename: string
  path: string
  size: number
  uploaded_at: string
  status: 'pending' | 'converting' | 'completed' | 'failed'
  markdown_path: string | null
}

/** PDF上传响应 */
export interface PDFUploadResponse {
  success: boolean
  message: string
  file: {
    filename: string
    path: string
    size: number
    uploaded_at: string
  }
}

/** PDF转换响应 */
export interface PDFConvertResponse {
  success: boolean
  message: string
  markdown_path: string
}

/** 上传PDF文件 */
export async function uploadPDF(file: File): Promise<PDFUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  
  const authStorage = localStorage.getItem('auth-storage')
  let token: string | null = null
  
  if (authStorage) {
    try {
      const parsed = JSON.parse(authStorage)
      token = parsed.state?.token || null
    } catch {
      // ignore
    }
  }
  
  const res = await fetch('/api/pdf/upload', {
    method: 'POST',
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    body: formData,
  })
  
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `Upload failed: ${res.status}`)
  }
  
  return res.json()
}

/** 获取PDF列表 */
export function getPDFList(page = 1, pageSize = 20, status?: string) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (status) params.set('status', status)
  return request<{ items: PDFFile[]; total: number }>(`/pdf/list?${params}`)
}

/** 转换PDF */
export function convertPDF(filename: string) {
  return request<PDFConvertResponse>(`/pdf/convert?filename=${encodeURIComponent(filename)}`, {
    method: 'POST',
  })
}

/** 修复无效Frontmatter */
export function fixFrontmatter(id: string) {
  return request<{ success: boolean; message: string }>(`/fix/frontmatter/${encodeURIComponent(id)}`, {
    method: 'POST',
  })
}

/** 删除不完整论文并重新生成（异步任务） */
export function regeneratePaper(id: string) {
  return request<{ task_id: string; status: string; message: string; deleted_paper?: string; deleted_entities?: string[]; deleted_concepts?: string[] }>(`/fix/regenerate-paper/${encodeURIComponent(id)}`, {
    method: 'POST',
  })
}

/** 查询后台任务状态 */
export function getTaskStatus(taskId: string) {
  return request<{ status: string; message: string; deleted_paper?: string; deleted_entities?: string[]; deleted_concepts?: string[]; regenerated_files?: string[]; finished_at?: string }>(`/fix/task-status/${taskId}`)
}

/** 修复断裂链接 */
export function fixBrokenLink(id: string, action: 'remove' | 'replace', brokenLink: string, replacement?: string) {
  const body: Record<string, string> = { action, broken_link: brokenLink }
  if (replacement) body.replacement = replacement
  return request<{ success: boolean; message: string }>(`/fix/broken-link/${encodeURIComponent(id)}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** 合并重复实体 */
export function mergeEntities(keepPage: string, removePage: string) {
  return request<{ success: boolean; message: string; updated_refs?: number }>(`/fix/merge-entities`, {
    method: 'POST',
    body: JSON.stringify({ keep_page: keepPage, remove_page: removePage }),
  })
}

/** 删除PDF */
export function deletePDF(filename: string) {
  return request<{ success: boolean; message: string }>(`/pdf/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  })
}

/** 健康体检报告 */
export interface HealthCheckReport {
  success: boolean
  report: {
    timestamp: string
    vault_path: string
    wiki_path: string
    layer: string
    summary: {
      total_pages: number
      health_score: number
      total_issues: number
    }
    stats: Record<string, number>
    issues: {
      severity: 'error' | 'warning' | 'info'
      type: string
      count?: number
      pages?: string[]
      message?: string
      threshold?: number
    }[]
    details: Record<string, unknown[]>
  }
}

/** 运行健康体检 */
export function runHealthCheck(layer: string = 'all') {
  return request<HealthCheckReport>(`/health-check?layer=${layer}`, {
    method: 'POST',
  })
}
