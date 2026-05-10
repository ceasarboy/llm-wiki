import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Tabs, List, Tag, Input, Empty, Spin, Typography, Button, Card, Segmented, message, Pagination } from 'antd'
import { SearchOutlined, BookOutlined, ClearOutlined, FileTextOutlined, ArrowLeftOutlined, ReloadOutlined, EditOutlined, EyeOutlined, ColumnWidthOutlined, SaveOutlined, FormOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPages, getSystemStatus, searchKnowledge, getRawDocuments, getRawDocument, saveRawDocument, getRawPdfUrl } from '../services/api'
import { renderMarkdown } from '../utils/markdown'
import { useAuthStore } from '../stores/useAuthStore'
import { hasRole } from '../stores/useAuthStore'

const { Title, Text } = Typography

const typeLabels: Record<string, string> = {
  entity: '实体',
  concept: '概念',
  paper: '论文',
  survey: '综述',
  comparison: '对比',
  synthesis: '综合',
  faq: 'FAQ',
  exploration: '探索',
  raw: '原文',
}

const typeColors: Record<string, string> = {
  entity: 'blue',
  concept: 'purple',
  paper: 'green',
  survey: 'orange',
  comparison: 'magenta',
  synthesis: 'cyan',
  faq: 'gold',
  exploration: 'default',
  raw: 'geekblue',
}

export default function KnowledgePage() {
  const { type: urlType } = useParams()
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const canEdit = hasRole(user, ['admin', 'core', 'maintainer'])
  const queryClient = useQueryClient()

  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [activeTab, setActiveTab] = useState(urlType || 'all')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [selectedRawId, setSelectedRawId] = useState<string | null>(null)
  const [editMode, setEditMode] = useState<'preview' | 'edit' | 'split'>('preview')
  const [editContent, setEditContent] = useState('')
  const [editFilename, setEditFilename] = useState('')
  const [hasPdf, setHasPdf] = useState(false)
  const prevSelectedRawId = useRef<string | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery.trim())
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const { data: pagesData, isLoading: pagesLoading, refetch: refetchPages } = useQuery({
    queryKey: ['pages', activeTab === 'all' ? undefined : activeTab, currentPage, pageSize],
    queryFn: () => getPages(activeTab === 'all' ? undefined : activeTab, currentPage, pageSize),
    enabled: !debouncedQuery && activeTab !== 'raw',
  })

  const { data: searchData, isLoading: searchLoading, refetch: refetchSearch } = useQuery({
    queryKey: ['search', debouncedQuery, activeTab],
    queryFn: () => searchKnowledge(debouncedQuery, activeTab === 'all' ? undefined : activeTab),
    enabled: !!debouncedQuery && activeTab !== 'raw',
  })

  const { data: statusData, refetch: refetchStatus } = useQuery({
    queryKey: ['status'],
    queryFn: getSystemStatus,
  })

  const { data: rawData, isLoading: rawLoading, refetch: refetchRaw } = useQuery({
    queryKey: ['rawDocuments', debouncedQuery],
    queryFn: () => getRawDocuments(1, 200, debouncedQuery || undefined),
    enabled: activeTab === 'raw',
  })

  const { data: rawDetail } = useQuery({
    queryKey: ['rawDocument', selectedRawId],
    queryFn: () => getRawDocument(selectedRawId!),
    enabled: !!selectedRawId && activeTab === 'raw',
  })

  const saveMutation = useMutation({
    mutationFn: ({ id, content, filename }: { id: string; content: string; filename?: string }) =>
      saveRawDocument(id, content, filename),
    onSuccess: (data) => {
      message.success('保存成功')
      const effectiveId = data.new_id || selectedRawId
      if (data.new_id && data.new_id !== selectedRawId) {
        setSelectedRawId(data.new_id)
        prevSelectedRawId.current = data.new_id
      }
      queryClient.invalidateQueries({ queryKey: ['rawDocuments'] })
      queryClient.invalidateQueries({ queryKey: ['rawDocument', effectiveId] })
    },
    onError: (error: Error) => {
      message.error(`保存失败：${error.message}`)
    },
  })

  useEffect(() => {
    if (selectedRawId && rawDetail) {
      if (selectedRawId !== prevSelectedRawId.current) {
        setEditContent(rawDetail.content)
        setEditFilename(rawDetail.title)
        setEditMode('preview')
        prevSelectedRawId.current = selectedRawId
      }
      fetch(getRawPdfUrl(selectedRawId), { method: 'HEAD' })
        .then(res => setHasPdf(res.ok))
        .catch(() => setHasPdf(false))
    }
  }, [selectedRawId, rawDetail])

  const handleSave = useCallback(() => {
    if (!selectedRawId) return
    const filenameChanged = editFilename !== rawDetail?.title
    saveMutation.mutate({
      id: selectedRawId,
      content: editContent,
      filename: filenameChanged ? editFilename : undefined,
    })
  }, [selectedRawId, editContent, editFilename, rawDetail, saveMutation])

  const typeCounts = (statusData as { counts_by_type?: Record<string, number> })?.counts_by_type || {}

  const handleTabChange = (key: string) => {
    setActiveTab(key)
    setCurrentPage(1)
    setSelectedRawId(null)
    if (key === 'all') {
      navigate('/knowledge')
    } else {
      navigate(`/knowledge/${key}`)
    }
  }

  const handleClearSearch = () => {
    setSearchQuery('')
    setDebouncedQuery('')
  }

  const handleRefresh = () => {
    refetchPages()
    refetchSearch()
    refetchStatus()
    refetchRaw()
  }

  const displayData = debouncedQuery
    ? { items: searchData?.results || [], total: searchData?.results?.length || 0 }
    : pagesData

  const tabItems = [
    { key: 'all', label: `全部 (${statusData?.total_docs || 0})` },
    ...Object.entries(typeLabels).filter(([k]) => k !== 'raw').map(([key, label]) => ({
      key,
      label: `${label} (${typeCounts[key] || 0})`,
    })),
    { key: 'raw', label: `原文 (${rawData?.total || 0})` },
  ]

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const renderedContent = useMemo(() => {
    if (!rawDetail?.content) return ''
    return renderMarkdown(rawDetail.content, selectedRawId || undefined)
  }, [rawDetail?.content, selectedRawId])

  const renderRawContent = () => {
    if (selectedRawId && rawDetail) {

      return (
        <div>
          <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
            <Button icon={<ArrowLeftOutlined />} onClick={() => setSelectedRawId(null)}>
              返回列表
            </Button>
            <div className="flex items-center gap-2">
              {canEdit && (
                <Segmented
                  value={editMode}
                  onChange={(v) => setEditMode(v as 'preview' | 'edit' | 'split')}
                  options={[
                    { label: '预览', value: 'preview', icon: <EyeOutlined /> },
                    { label: '编辑', value: 'edit', icon: <EditOutlined /> },
                    { label: '分屏', value: 'split', icon: <ColumnWidthOutlined />, disabled: !hasPdf },
                  ]}
                />
              )}
            </div>
          </div>

          {editMode === 'split' && hasPdf ? (
            <div className="flex gap-4" style={{ height: 'calc(100vh - 220px)' }}>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <div className="mb-2 flex items-center gap-2">
                  <FormOutlined style={{ color: 'var(--text-secondary)' }} />
                  <Input
                    value={editFilename}
                    onChange={(e) => {
                      let val = e.target.value
                      if (val.endsWith('.md')) val = val.slice(0, -3)
                      setEditFilename(val)
                    }}
                    style={{ maxWidth: 300, fontWeight: 600 }}
                    addonAfter=".md"
                  />
                  <Button
                    type="primary"
                    icon={<SaveOutlined />}
                    onClick={handleSave}
                    loading={saveMutation.isPending}
                    disabled={editContent === rawDetail.content && editFilename === rawDetail.title}
                  >
                    保存
                  </Button>
                </div>
                <textarea
                  className="raw-editor-textarea"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  style={{ flex: 1, padding: 16, borderRadius: 8, outline: 'none' }}
                />
              </div>
              <div style={{ flex: 1, minWidth: 0, height: '100%' }}>
                <iframe
                  src={getRawPdfUrl(selectedRawId) + '#toolbar=0&navpanes=0'}
                  style={{ width: '100%', height: '100%', border: 0, borderRadius: 8, display: 'block' }}
                  title="PDF Viewer"
                />
              </div>
            </div>
          ) : (
            <div className="flex gap-4" style={{ height: 'calc(100vh - 220px)' }}>
              <div className="flex-1 min-w-0" style={{ display: 'flex', flexDirection: 'column' }}>
                {canEdit && editMode !== 'preview' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
                    <div className="mb-2 flex items-center gap-2">
                      <FormOutlined style={{ color: 'var(--text-secondary)' }} />
                      <Input
                        value={editFilename}
                        onChange={(e) => {
                          let val = e.target.value
                          if (val.endsWith('.md')) val = val.slice(0, -3)
                          setEditFilename(val)
                        }}
                        style={{ maxWidth: 300, fontWeight: 600 }}
                        addonAfter=".md"
                      />
                      <Button
                        type="primary"
                        icon={<SaveOutlined />}
                        onClick={handleSave}
                        loading={saveMutation.isPending}
                        disabled={editContent === rawDetail.content && editFilename === rawDetail.title}
                      >
                        保存
                      </Button>
                    </div>
                    <textarea
                      className="raw-editor-textarea"
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      style={{ flex: 1, padding: 16, borderRadius: 8, outline: 'none' }}
                    />
                  </div>
                ) : (
                  <Card className="glass-card-flat" style={{ flex: 1, overflow: 'auto' }}>
                    <div className="mb-4 flex items-center justify-between">
                      <Title level={4} style={{ color: 'var(--text-primary)', margin: 0 }}>
                        {rawDetail.title}
                      </Title>
                      <Text type="secondary">
                        {formatSize(rawDetail.size)} · 更新于 {rawDetail.updated}
                      </Text>
                    </div>
                    <div
                      className="markdown-content"
                      style={{
                        maxHeight: 'calc(100vh - 320px)',
                        overflow: 'auto',
                        background: 'var(--bg-secondary)',
                        padding: 24,
                        borderRadius: 12,
                      }}
                      dangerouslySetInnerHTML={{ __html: renderedContent }}
                    />
                  </Card>
                )}
              </div>
            </div>
          )}
        </div>
      )
    }

    return (
      <Spin spinning={rawLoading}>
        {rawData?.items?.length ? (
          <List
            itemLayout="horizontal"
            dataSource={rawData.items}
            renderItem={(item) => (
              <List.Item
                className="cursor-pointer p-4 rounded-lg knowledge-list-item"
                onClick={() => setSelectedRawId(item.id)}
              >
                <List.Item.Meta
                  avatar={<FileTextOutlined style={{ fontSize: 24, color: 'var(--accent)' }} />}
                  title={<Text strong style={{ color: 'var(--text-primary)' }}>{item.title}</Text>}
                  description={
                    <Text type="secondary">
                      {formatSize(item.size)} · 更新于 {item.updated}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty description="暂无原文" />
        )}
      </Spin>
    )
  }

  return (
    <div className="py-6">
      <Title level={2} style={{ color: 'var(--text-primary)' }}>
        <BookOutlined className="mr-2" />
        知识库
      </Title>

      <div className="mb-6 flex gap-2">
        <Input
          size="large"
          placeholder={activeTab === 'raw' ? '搜索原文...' : '搜索知识库...'}
          prefix={<SearchOutlined />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="max-w-md"
          allowClear
        />
        <Button size="large" icon={<ReloadOutlined />} onClick={handleRefresh}>
          刷新
        </Button>
        {debouncedQuery && (
          <Button size="large" icon={<ClearOutlined />} onClick={handleClearSearch}>
            清除搜索
          </Button>
        )}
      </div>

      {debouncedQuery && activeTab !== 'raw' && (
        <div className="mb-4">
          <Text type="secondary">
            搜索 "{debouncedQuery}" 找到 {displayData?.items?.length || 0} 个结果
          </Text>
        </div>
      )}

      <Tabs activeKey={activeTab} onChange={handleTabChange} items={tabItems} />

      {activeTab === 'raw' ? (
        renderRawContent()
      ) : (
        <Spin spinning={pagesLoading || searchLoading}>
          <div style={{ maxHeight: 'calc(100vh - 300px)', overflow: 'auto' }}>
            {displayData?.items?.length ? (
              <List
                itemLayout="vertical"
                dataSource={displayData.items}
                renderItem={(item) => (
                  <List.Item
                    className="cursor-pointer p-4 rounded-lg knowledge-list-item"
                    onClick={() => navigate(`/knowledge/${item.id}`)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <Text strong style={{ color: 'var(--text-primary)', fontSize: 16 }}>
                            {item.title}
                          </Text>
                          <Tag color={typeColors[item.type]}>{typeLabels[item.type] || item.type}</Tag>
                        </div>
                        {item.summary && (
                          <Text type="secondary" className="line-clamp-2">{item.summary}</Text>
                        )}
                        <div className="mt-2 flex items-center gap-4">
                          {item.tags?.slice(0, 3).map((tag: string) => (
                            <Tag key={tag} className="text-xs">{tag}</Tag>
                          ))}
                          <Text type="secondary" className="text-xs">更新于 {item.updated}</Text>
                        </div>
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description={debouncedQuery ? `未找到 "${debouncedQuery}" 相关内容` : "暂无数据"} />
            )}
            {displayData?.items?.length && displayData?.total ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '16px 0' }}>
                <Pagination
                  current={currentPage}
                  pageSize={pageSize}
                  total={displayData.total}
                  showSizeChanger
                  pageSizeOptions={['20', '50', '100']}
                  onChange={(p, ps) => {
                    setCurrentPage(p)
                    if (ps !== pageSize) {
                      setPageSize(ps)
                      setCurrentPage(1)
                    }
                  }}
                  showTotal={(total) => `共 ${total} 条`}
                />
              </div>
            ) : null}
          </div>
        </Spin>
      )}
    </div>
  )
}
