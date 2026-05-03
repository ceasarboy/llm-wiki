import { useParams, useNavigate } from 'react-router-dom'
import { Card, Tag, Button, Spin, Empty, Typography, Space, message, Modal, Input, Alert, List, Drawer, Descriptions, Radio } from 'antd'
import { EditOutlined, HistoryOutlined, LinkOutlined, SaveOutlined, CloseOutlined, SyncOutlined, CheckCircleOutlined, ClockCircleOutlined, TeamOutlined, BulbOutlined, BookOutlined, ApartmentOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPageDetail, savePage, submitManualReview, recheckPage, getPageHistory, getHistoryVersion, getGraphNeighbors } from '../services/api'
import type { ManualReviewRequest } from '../services/api'
import { useMemo, useState, useEffect, useRef, useCallback } from 'react'
import { useAuthStore, hasRole } from '../stores/useAuthStore'
import { renderMarkdown } from '../utils/markdown'
import cytoscape from 'cytoscape'
// @ts-ignore cytoscape-fcose has no types
import fcose from 'cytoscape-fcose'

cytoscape.use(fcose)

const { Title, Text } = Typography
const { TextArea } = Input

const typeLabels: Record<string, string> = {
  entity: '实体',
  concept: '概念',
  paper: '论文',
  summary: '摘要',
  synthesis: '综述',
  comparison: '对比',
  faq: 'FAQ',
  exploration: '探索',
}

const statusColors: Record<string, string> = {
  draft: 'default',
  generated: 'processing',
  reviewed: 'success',
  stable: 'success',
  rejected: 'error',
  requires_manual_review: 'warning',
}

export default function PageDetailPage() {
  const { type, id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fullId = id ? `${type}/${id}` : type || ''
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [historyDrawerVisible, setHistoryDrawerVisible] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [reviewModalVisible, setReviewModalVisible] = useState(false)
  const [reviewAction, setReviewAction] = useState<'approve' | 'reject'>('approve')
  const [reviewComment, setReviewComment] = useState('')
  const [reviewerName, setReviewerName] = useState('')
  const { user } = useAuthStore()
  
  const canEdit = hasRole(user, ['admin', 'core', 'maintainer'])
  const isAdmin = hasRole(user, ['admin'])

  const { data: page, isLoading, error } = useQuery({
    queryKey: ['pageDetail', fullId],
    queryFn: () => getPageDetail(fullId),
    enabled: !!fullId,
  })

  const entityMatches = useMemo(() =>
    [...(page?.content?.matchAll(/\[\[entities\/([^\]|]+)(?:\|([^\]]+))?\]\]/g) || [])],
    [page?.content]
  )
  const conceptMatches = useMemo(() =>
    [...(page?.content?.matchAll(/\[\[concepts\/([^\]|]+)(?:\|([^\]]+))?\]\]/g) || [])],
    [page?.content]
  )
  const paperMatches = useMemo(() =>
    [...(page?.content?.matchAll(/\[\[papers\/([^\]|]+)(?:\|([^\]]+))?\]\]/g) || [])],
    [page?.content]
  )

  const saveMutation = useMutation({
    mutationFn: (content: string) => savePage(fullId, content),
    onSuccess: () => {
      message.success('保存成功')
      setIsEditing(false)
      queryClient.invalidateQueries({ queryKey: ['pageDetail', fullId] })
    },
    onError: () => {
      message.error('保存失败')
    },
  })

  const manualReviewMutation = useMutation({
    mutationFn: (data: ManualReviewRequest) => submitManualReview(fullId, data),
    onSuccess: () => {
      message.success('审核完成')
      setReviewModalVisible(false)
      setReviewComment('')
      queryClient.invalidateQueries({ queryKey: ['pageDetail', fullId] })
    },
    onError: () => {
      message.error('审核失败')
    },
  })

  const recheckMutation = useMutation({
    mutationFn: () => recheckPage(fullId, ''),
    onSuccess: () => {
      message.success('复审任务已启动')
      queryClient.invalidateQueries({ queryKey: ['pageDetail', fullId] })
    },
    onError: () => {
      message.error('复审失败')
    },
  })

  const { data: historyData, isLoading: historyLoading, refetch: refetchHistory } = useQuery({
    queryKey: ['pageHistory', fullId],
    queryFn: () => getPageHistory(fullId),
    enabled: historyDrawerVisible,
  })

  const { data: versionDetail, isLoading: versionLoading } = useQuery({
    queryKey: ['historyVersion', fullId, selectedVersion],
    queryFn: () => getHistoryVersion(fullId, selectedVersion!),
    enabled: selectedVersion !== null,
  })

  const handleOpenObsidian = () => {
    if (page) {
      const url = `obsidian://open?vault=Obsidian%20Vault&file=${encodeURIComponent(page.id)}`
      window.open(url, '_blank')
      message.info('正在 Obsidian 中打开...')
    }
  }

  const handleWikiLinkClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement
    if (target.classList.contains('wiki-link')) {
      const linkId = target.getAttribute('data-link')
      if (linkId) {
        navigate(`/knowledge/${linkId}`)
      }
    }
  }

  const handleEdit = () => {
    if (page) {
      setEditContent(page.content)
      setIsEditing(true)
    }
  }

  const handleSave = () => {
    saveMutation.mutate(editContent)
  }

  const handleCancel = () => {
    setIsEditing(false)
    setEditContent('')
  }

  const handleManualReview = () => {
    setReviewModalVisible(true)
  }

  const handleRecheck = () => {
    Modal.confirm({
      title: '确认复审',
      content: '确定要重新生成此页面吗？将使用审核意见作为生成提示。',
      onOk: () => recheckMutation.mutate(),
    })
  }

  const handleHistoryClick = () => {
    setHistoryDrawerVisible(true)
    refetchHistory()
  }

  const handleVersionClick = (version: number) => {
    setSelectedVersion(version)
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const formattedContent = useMemo(() => {
    if (!page) return ''
    return renderMarkdown(page.content)
  }, [page])

  const needsImprovement = page?.status === 'requires_manual_review' || page?.status === 'needs_revision'
  const reviewIssuesRaw = page?.frontmatter?.review_issues
  const reviewIssues: string[] = Array.isArray(reviewIssuesRaw) ? reviewIssuesRaw as string[] : []
  const manualReviewStatus = page?.frontmatter?.manual_review || 'pending'
  const pageReviewComment = page?.frontmatter?.review_comment as string | undefined
  const pageReviewer = page?.frontmatter?.reviewer as string | undefined
  const pageReviewedAt = page?.frontmatter?.reviewed_at as string | undefined

  if (isLoading) {
    return <div className="text-center py-20"><Spin size="large" /></div>
  }

  if (error || !page) {
    return <Empty description="页面不存在" className="py-20" />
  }

  return (
    <div className="max-w-4xl mx-auto py-6">
      {needsImprovement && (reviewIssues.length > 0 || pageReviewComment) && (
        <Alert
          type="error"
          showIcon
          className="mb-4"
          message={<span style={{ color: 'var(--error)', fontWeight: 'bold' }}>待完善</span>}
          description={
            <div>
              {pageReviewer && pageReviewedAt && (
                <p style={{ fontWeight: 'bold', marginBottom: 8 }}>
                  审核人：{pageReviewer} · 审核时间：{pageReviewedAt}
                </p>
              )}
              {pageReviewComment && (
                <div style={{ marginBottom: 8 }}>
                  <p style={{ fontWeight: 'bold', marginBottom: 4 }}>审核意见：</p>
                  <p style={{ margin: 0 }}>{pageReviewComment}</p>
                </div>
              )}
              {reviewIssues.length > 0 && (
                <div>
                  <p style={{ fontWeight: 'bold', marginBottom: 8 }}>上次审核不通过的意见：</p>
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {reviewIssues.map((issue, idx) => (
                      <li key={idx}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          }
        />
      )}

      <Card className="mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <Title level={2} style={{ color: 'var(--text-primary)', marginBottom: 8 }}>
              📄 {page.title}
            </Title>
            <Space>
              <Tag color="blue">{typeLabels[page.type] || page.type}</Tag>
              <Tag color={statusColors[page.status] || 'default'}>
                {needsImprovement ? <span style={{ color: 'var(--error)', fontWeight: 'bold' }}>待完善</span> : page.status}
              </Tag>
              {manualReviewStatus === 'approved' && (
                <Tag color="green" icon={<CheckCircleOutlined />}>已人工审核</Tag>
              )}
              <Text type="secondary">更新于 {page.updated}</Text>
            </Space>
          </div>
          <Space>
            <Button icon={<LinkOutlined />} onClick={handleOpenObsidian}>在 Obsidian 中打开</Button>
            {canEdit && !isEditing && (
              <Button icon={<EditOutlined />} type="primary" onClick={handleEdit}>编辑</Button>
            )}
            {isEditing && (
              <>
                <Button icon={<SaveOutlined />} type="primary" onClick={handleSave} loading={saveMutation.isPending}>保存</Button>
                <Button icon={<CloseOutlined />} onClick={handleCancel}>取消</Button>
              </>
            )}
            {isAdmin && page?.status === 'pending' && pageReviewComment && !isEditing && (
              <Button 
                icon={<SyncOutlined />} 
                onClick={handleRecheck}
                loading={recheckMutation.isPending}
              >
                复审
              </Button>
            )}
            {isAdmin && manualReviewStatus !== 'approved' && !isEditing && (
              <Button icon={<CheckCircleOutlined />} onClick={handleManualReview} loading={manualReviewMutation.isPending}>
                人工审核
              </Button>
            )}
            <Button icon={<HistoryOutlined />} onClick={handleHistoryClick}>历史版本</Button>
          </Space>
        </div>
      </Card>

      {isEditing ? (
        <Card className="mb-6">
          <TextArea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            rows={25}
            style={{ fontFamily: 'monospace', fontSize: 14 }}
          />
        </Card>
      ) : (
        <Card className="mb-6">
          <div
            className="markdown-content"
            style={{ color: 'var(--text-primary)' }}
            dangerouslySetInnerHTML={{ __html: formattedContent }}
            onClick={handleWikiLinkClick}
          />
        </Card>
      )}

      {!isEditing && page.type === 'paper' && (entityMatches.length > 0 || conceptMatches.length > 0) && (
        <Card className="mb-6" style={{ borderColor: 'var(--border-color)' }}>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {entityMatches.length > 0 && (
              <div style={{ flex: '1 1 300px', minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <TeamOutlined style={{ color: 'var(--success)', fontSize: '16px' }} />
                  <span style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>
                    提取的实体
                  </span>
                  <Tag color="green" style={{ marginLeft: '4px' }}>{entityMatches.length}</Tag>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {entityMatches.map((m, i) => {
                    const linkId = `entities/${m[1].replace('.md', '').trim()}`
                    const display = m[2] || m[1].replace('.md', '').split('/').pop() || m[1]
                    return (
                      <Tag
                        key={i}
                        color="green"
                        style={{ cursor: 'pointer', fontSize: '13px', padding: '2px 8px' }}
                        onClick={() => navigate(`/knowledge/${linkId}`)}
                      >
                        {display}
                      </Tag>
                    )
                  })}
                </div>
              </div>
            )}
            
            {entityMatches.length > 0 && conceptMatches.length > 0 && (
              <div style={{ width: '1px', background: 'var(--border-color)', alignSelf: 'stretch' }} />
            )}
            
            {conceptMatches.length > 0 && (
              <div style={{ flex: '1 1 300px', minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <BulbOutlined style={{ color: 'var(--warning)', fontSize: '16px' }} />
                  <span style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>
                    涉及的概念
                  </span>
                  <Tag color="orange" style={{ marginLeft: '4px' }}>{conceptMatches.length}</Tag>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {conceptMatches.map((m, i) => {
                    const linkId = `concepts/${m[1].replace('.md', '').trim()}`
                    const display = m[2] || m[1].replace('.md', '').split('/').pop() || m[1]
                    return (
                      <Tag
                        key={i}
                        color="orange"
                        style={{ cursor: 'pointer', fontSize: '13px', padding: '2px 8px' }}
                        onClick={() => navigate(`/knowledge/${linkId}`)}
                      >
                        {display}
                      </Tag>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {!isEditing && (page.type === 'entity' || page.type === 'concept') && paperMatches.length > 0 && (
        <Card className="mb-6" style={{ borderColor: 'var(--border-color)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <BookOutlined style={{ color: 'var(--accent)', fontSize: '16px' }} />
            <span style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>
              相关论文
            </span>
            <Tag color="blue" style={{ marginLeft: '4px' }}>{paperMatches.length}</Tag>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {paperMatches.map((m, i) => {
              const linkId = `papers/${m[1].replace('.md', '').trim()}`
              const display = m[2] || m[1].replace('.md', '').replace(/_论文$/, '').split('/').pop() || m[1]
              return (
                <div
                  key={i}
                  style={{
                    padding: '8px 12px',
                    background: 'var(--bg-tertiary)',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    border: '1px solid var(--border)',
                  }}
                  onClick={() => navigate(`/knowledge/${linkId}`)}
                  onMouseEnter={(e) => {
                    const el = e.currentTarget
                    el.style.borderColor = 'var(--accent)'
                    el.style.transform = 'translateX(4px)'
                  }}
                  onMouseLeave={(e) => {
                    const el = e.currentTarget
                    el.style.borderColor = 'var(--border)'
                    el.style.transform = 'translateX(0)'
                  }}
                >
                  <span style={{ color: 'var(--accent)', fontSize: '14px' }}>📄 {display}</span>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {!isEditing && <MiniGraphCard pageId={fullId} pageType={page.type} />}

      {page.frontmatter && Object.keys(page.frontmatter).length > 0 && !isEditing && (
        <Card title="元数据" className="mb-6">
          <pre className="text-sm overflow-auto" style={{ color: 'var(--text-secondary)' }}>
            {JSON.stringify(page.frontmatter, null, 2)}
          </pre>
        </Card>
      )}

      {page.tags?.length > 0 && !isEditing && (
        <Card title="标签">
          <Space wrap>
            {page.tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </Space>
        </Card>
      )}

      <Drawer
        title="历史版本"
        placement="right"
        width={720}
        open={historyDrawerVisible}
        onClose={() => {
          setHistoryDrawerVisible(false)
          setSelectedVersion(null)
        }}
      >
        <div style={{ display: 'flex', height: '100%' }}>
          <div style={{ width: 280, borderRight: '1px solid var(--border-color)', paddingRight: 16, overflow: 'auto' }}>
            {historyLoading ? (
              <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
            ) : historyData?.items?.length === 0 ? (
              <Empty description="暂无历史版本" />
            ) : (
              <List
                dataSource={historyData?.items || []}
                renderItem={(item) => (
                  <List.Item
                    onClick={() => handleVersionClick(item.version)}
                    style={{
                      cursor: 'pointer',
                      backgroundColor: selectedVersion === item.version ? 'var(--bg-secondary)' : 'transparent',
                      borderRadius: 4,
                      padding: '8px 12px',
                    }}
                  >
                    <List.Item.Meta
                      title={<span><ClockCircleOutlined style={{ marginRight: 8 }} />版本 {item.version}</span>}
                      description={
                        <div>
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            {item.saved_at || '未知时间'}
                          </div>
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            {item.save_reason || '无修改说明'}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                            大小: {formatSize(item.size)}
                          </div>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </div>
          <div style={{ flex: 1, paddingLeft: 16, overflow: 'auto' }}>
            {selectedVersion === null ? (
              <Empty description="请选择一个历史版本查看" style={{ marginTop: 100 }} />
            ) : versionLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : versionDetail ? (
              <div>
                <Descriptions bordered size="small" column={1} style={{ marginBottom: 16 }}>
                  <Descriptions.Item label="版本号">{versionDetail.version}</Descriptions.Item>
                  <Descriptions.Item label="保存时间">{versionDetail.saved_at || '未知'}</Descriptions.Item>
                  <Descriptions.Item label="修改说明">{versionDetail.save_reason || '无'}</Descriptions.Item>
                  <Descriptions.Item label="文件名">{versionDetail.filename}</Descriptions.Item>
                </Descriptions>
                <Card title="内容预览" size="small" style={{ maxHeight: 500, overflow: 'auto' }}>
                  <div
                    className="markdown-content"
                    style={{ fontSize: '14px', lineHeight: '1.8' }}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(versionDetail.content || '') }}
                  />
                </Card>
              </div>
            ) : (
              <Empty description="无法加载版本详情" />
            )}
          </div>
        </div>
      </Drawer>

      <Modal
        title="人工审核"
        open={reviewModalVisible}
        onOk={() => {
          manualReviewMutation.mutate({
            action: reviewAction,
            comment: reviewComment,
            reviewer: reviewerName
          })
        }}
        onCancel={() => setReviewModalVisible(false)}
        confirmLoading={manualReviewMutation.isPending}
      >
        <div style={{ marginBottom: 16 }}>
          <Text>审核结果：</Text>
          <Radio.Group value={reviewAction} onChange={(e) => setReviewAction(e.target.value)}>
            <Radio value="approve">通过</Radio>
            <Radio value="reject">不通过</Radio>
          </Radio.Group>
        </div>
        
        <div style={{ marginBottom: 16 }}>
          <Text>审核人：</Text>
          <Input 
            value={reviewerName} 
            onChange={(e) => setReviewerName(e.target.value)}
            placeholder="请输入审核人姓名"
            style={{ width: 200 }}
          />
        </div>
        
        <div>
          <Text>审核意见：</Text>
          <TextArea
            value={reviewComment}
            onChange={(e) => setReviewComment(e.target.value)}
            rows={4}
            placeholder="请输入审核意见..."
          />
        </div>
      </Modal>
    </div>
  )
}

const typeColors: Record<string, string> = {
  paper: '--accent',
  entity: '--success',
  concept: '--warning',
  synthesis: '--purple',
  summary: '--cyan',
}

function getThemeColor(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
}

function getTypeColor(type: string): string {
  const varName = typeColors[type]
  return varName ? getThemeColor(varName) : getThemeColor('--text-muted')
}

function MiniGraphCard({ pageId, pageType: _pageType }: { pageId: string; pageType: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const navigate = useNavigate()

  const { data: graphData, isLoading } = useQuery({
    queryKey: ['graphNeighbors', pageId],
    queryFn: () => getGraphNeighbors(pageId, 1),
    enabled: !!pageId,
    retry: 0,
  })

  const initGraph = useCallback(() => {
    if (!containerRef.current || !graphData || graphData.nodes.length === 0) return

    if (cyRef.current) {
      cyRef.current.destroy()
    }

    const centerId = graphData.metadata?.centerNode || pageId

    const elements = [
      ...graphData.nodes.map(n => ({
        data: {
          id: n.id,
          label: n.label.length > 20 ? n.label.substring(0, 18) + '...' : n.label,
          nodeType: n.type,
          isCenter: n.id === centerId,
        }
      })),
      ...graphData.edges.map(e => ({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
        }
      }))
    ]

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': '10px',
            'color': getThemeColor('--text-primary'),
            'text-outline-color': getThemeColor('--bg-primary'),
            'text-outline-width': 2,
            'width': 30,
            'height': 30,
            'border-width': 2,
            'border-color': 'data(nodeTypeColor)',
            'background-color': 'data(nodeTypeColor)',
          } as any,
        },
        {
          selector: 'node[isCenter]',
          style: {
            'width': 45,
            'height': 45,
            'font-size': '11px',
            'font-weight': 'bold',
            'border-width': 3,
            'border-color': getThemeColor('--accent'),
          } as any,
        },
        {
          selector: 'edge',
          style: {
            'width': 1.5,
            'line-color': getThemeColor('--border'),
            'target-arrow-color': getThemeColor('--border'),
            'curve-style': 'bezier',
            'opacity': 0.6,
          } as any,
        },
      ],
      layout: {
        name: 'fcose',
        animate: false,
        nodeSeparation: 60,
        idealEdgeLength: 80,
      } as any,
    })

    cy.nodes().forEach(node => {
      const nodeType = node.data('nodeType')
      node.data('nodeTypeColor', getTypeColor(nodeType))
    })

    cy.on('tap', 'node', (evt) => {
      const nodeId = evt.target.id()
      navigate(`/knowledge/${nodeId}`)
    })

    cyRef.current = cy
  }, [graphData, pageId, navigate])

  useEffect(() => {
    initGraph()
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy()
        cyRef.current = null
      }
    }
  }, [initGraph])

  if (isLoading) {
    return (
      <Card className="mb-6" style={{ borderColor: 'var(--border-color)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
          <ApartmentOutlined style={{ color: 'var(--accent)', fontSize: '16px' }} />
          <span style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>关联图谱</span>
        </div>
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      </Card>
    )
  }

  if (!graphData || graphData.nodes.length <= 1) return null

  return (
    <Card className="mb-6" style={{ borderColor: 'var(--border-color)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
        <ApartmentOutlined style={{ color: 'var(--accent)', fontSize: '16px' }} />
        <span style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>关联图谱</span>
        <Tag color="purple" style={{ marginLeft: '4px' }}>{graphData.nodes.length} 节点</Tag>
        <Tag color="cyan" style={{ marginLeft: '2px' }}>{graphData.edges.length} 关系</Tag>
      </div>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
        {Object.entries(typeColors).map(([type, colorVar]) => (
          <span key={type} style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: `var(${colorVar})`, marginRight: 4 }} />
            {type === 'paper' ? '论文' : type === 'entity' ? '实体' : type === 'concept' ? '概念' : type === 'synthesis' ? '综合' : '摘要'}
          </span>
        ))}
      </div>
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: Math.min(300, Math.max(200, graphData.nodes.length * 25)),
          background: 'var(--bg-primary)',
          borderRadius: 8,
          border: '1px solid var(--border)',
        }}
      />
    </Card>
  )
}
