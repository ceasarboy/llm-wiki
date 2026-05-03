import { Card, Row, Col, Progress, Statistic, Tag, Button, Typography, Divider, Collapse, List, Spin, Empty, Space, Badge, Segmented, Table, Popconfirm, message as antMessage, Modal, Select } from 'antd'
import { CheckCircleOutlined, SyncOutlined, WarningOutlined, DashboardOutlined, ReloadOutlined, MedicineBoxOutlined, BugOutlined, InfoCircleOutlined, DeleteOutlined, SwapOutlined, MergeCellsOutlined, ToolOutlined, RedoOutlined } from '@ant-design/icons'
import { useQuery, useMutation } from '@tanstack/react-query'
import { getSystemStatus, runHealthCheck, fixFrontmatter, regeneratePaper, fixBrokenLink, mergeEntities, getTaskStatus } from '../services/api'
import type { HealthCheckReport } from '../services/api'
import { useState, useRef, useEffect } from 'react'

const { Title, Text } = Typography

const severityConfig: Record<string, { color: string; icon: React.ReactNode; label: string; tagColor: string }> = {
  error: { color: 'var(--color-error, #ff4d4f)', icon: <BugOutlined />, label: '错误', tagColor: 'error' },
  warning: { color: 'var(--color-warning, #faad14)', icon: <WarningOutlined />, label: '警告', tagColor: 'warning' },
  info: { color: 'var(--color-info, #1890ff)', icon: <InfoCircleOutlined />, label: '提示', tagColor: 'processing' },
}

const issueTypeLabels: Record<string, string> = {
  orphan_pages: '孤儿页面（可能被文本引用但缺少[[]]链接）',
  unresolved_conflicts: '未解决矛盾',
  invalid_frontmatter: '无效Frontmatter',
  no_source_id: '实体/概念无Source',
  broken_papers: '论文不完整',
  broken_links: '交叉引用断裂',
  duplicate_entities: '重复实体/概念',
  missing_concepts: '缺失概念页面',
  llm_concept_suggestions: 'LLM概念建议',
  quality_samples: '质量抽检',
  read_error: '读取错误',
  system: '系统错误',
  llm_concept_error: 'LLM分析错误',
}

const issueTypeDesc: Record<string, string> = {
  orphan_pages: '未被任何页面引用且不在索引中的页面',
  unresolved_conflicts: '包含未解决的 [Conflict: ...] 标记的页面',
  invalid_frontmatter: 'Frontmatter 缺失或不完整（缺少 title 字段）。点击"自动修复"可从内容中提取标题写入Frontmatter。',
  no_source_id: '实体或概念页面中没有任何 [Source: ...] 标注',
  broken_papers: '缺少必要章节或内容不足的论文页面。点击"删除并重新生成"将删除论文及其关联的实体和概念，然后从源文件重新生成。',
  broken_links: '引用了不存在的 Wiki 页面链接。点击"删除链接"可移除断裂引用。',
  duplicate_entities: '可能重复的实体或概念（英文名匹配）。选择保留项和删除项后点击"合并"。',
  missing_concepts: '被引用但没有对应页面的概念（与孤儿页面相反：孤儿=存在但未被引用，缺失=被引用但不存在）',
  llm_concept_suggestions: 'LLM 分析后建议创建的概念页面',
  quality_samples: '随机抽样的页面质量评估',
}

function DetailTable({ issueType, details, onFix }: { issueType: string; details: unknown[]; onFix: (action: string, data: Record<string, unknown>) => void }) {
  if (!details || details.length === 0) return null

  const items = details as Record<string, unknown>[]

  if (issueType === 'invalid_frontmatter') {
    const columns = [
      { title: '页面', dataIndex: 'page', key: 'page', render: (v: string) => <Text code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v}</Text> },
      { title: '原因', dataIndex: 'reason', key: 'reason', render: (v: string) => <Tag color="warning">{v === 'missing_title' ? '缺少title' : '无效'}</Tag> },
      { title: '操作', key: 'action', render: (_: unknown, record: Record<string, unknown>) => (
        <Popconfirm title="确认自动修复Frontmatter？" description="将从内容中提取标题写入Frontmatter" onConfirm={() => onFix('fix_frontmatter', record)}>
          <Button size="small" type="primary" icon={<ToolOutlined />}>自动修复</Button>
        </Popconfirm>
      )},
    ]
    return <Table columns={columns} dataSource={items} rowKey="page" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  if (issueType === 'broken_papers') {
    const columns = [
      { title: '页面', dataIndex: 'page', key: 'page', render: (v: string) => <Text code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v}</Text> },
      { title: '标题', dataIndex: 'title', key: 'title', render: (v: string) => <Text style={{ color: 'var(--text-primary)' }}>{v}</Text> },
      { title: '缺失章节', dataIndex: 'missing_sections', key: 'missing_sections', render: (v: string[]) => v?.map((s: string) => <Tag key={s} color="warning" style={{ fontSize: 11, margin: 1 }}>{s}</Tag>) },
      { title: '内容长度', dataIndex: 'body_length', key: 'body_length', render: (v: number) => <Text style={{ color: v > 500 ? 'var(--success)' : 'var(--warning)' }}>{v}</Text> },
      { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag>{v}</Tag> },
      { title: '操作', key: 'action', render: (_: unknown, record: Record<string, unknown>) => (
        <Popconfirm
          title="确认删除并重新生成？"
          description="将删除此论文及其关联的实体和概念，然后从源文件重新生成。此操作不可撤销。"
          onConfirm={() => onFix('regenerate_paper', record)}
        >
          <Button size="small" type="primary" danger icon={<RedoOutlined />}>删除并重新生成</Button>
        </Popconfirm>
      )},
    ]
    return <Table columns={columns} dataSource={items} rowKey="page" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  if (issueType === 'broken_links') {
    const columns = [
      { title: '页面', dataIndex: 'page', key: 'page', render: (v: string) => <Text code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v}</Text> },
      { title: '标题', dataIndex: 'title', key: 'title', render: (v: string) => <Text style={{ color: 'var(--text-primary)' }}>{v}</Text> },
      { title: '断裂链接', dataIndex: 'broken_links', key: 'broken_links', render: (v: string[]) => v?.map((s: string) => <Tag key={s} color="error" style={{ fontSize: 11, margin: 1 }}>{s}</Tag>) },
      { title: '数量', dataIndex: 'broken_count', key: 'broken_count', render: (v: number) => <Badge count={v} style={{ backgroundColor: '#ff4d4f' }} /> },
      { title: '操作', key: 'action', render: (_: unknown, record: Record<string, unknown>) => (
        <Space size="small">
          <Popconfirm title="确认删除此页面中的断裂链接？" description="将从页面内容中移除所有无法解析的链接" onConfirm={() => onFix('remove_broken_links', record)}>
            <Button size="small" icon={<DeleteOutlined />} danger>删除链接</Button>
          </Popconfirm>
        </Space>
      )},
    ]
    return <Table columns={columns} dataSource={items} rowKey="page" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  if (issueType === 'duplicate_entities') {
    const columns = [
      { title: '名称', dataIndex: 'name_key', key: 'name_key', render: (v: string) => <Text strong style={{ color: 'var(--accent)' }}>{v}</Text> },
      { title: '重复项', dataIndex: 'items', key: 'items', render: (v: Record<string, string>[]) => v?.map((item, i) => <Tag key={i} color="warning" style={{ fontSize: 11, margin: 1 }}>{item.title} ({item.type})</Tag>) },
      { title: '数量', dataIndex: 'count', key: 'count', render: (v: number) => <Badge count={v} style={{ backgroundColor: '#faad14' }} /> },
      { title: '操作', key: 'action', render: (_: unknown, record: Record<string, unknown>) => (
        <Button size="small" type="primary" icon={<MergeCellsOutlined />} onClick={() => onFix('merge_entities', record)}>合并</Button>
      )},
    ]
    return <Table columns={columns} dataSource={items} rowKey="name_key" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  if (issueType === 'orphan_pages') {
    const columns = [
      { title: '页面', dataIndex: 'page', key: 'page', render: (v: string) => <Text code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v}</Text> },
      { title: '标题', dataIndex: 'title', key: 'title', render: (v: string) => <Text style={{ color: 'var(--text-primary)' }}>{v}</Text> },
      { title: '类型', dataIndex: 'type', key: 'type', render: (v: string) => <Tag>{v}</Tag> },
    ]
    return <Table columns={columns} dataSource={items} rowKey="page" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  if (issueType === 'no_source_id') {
    const columns = [
      { title: '页面', dataIndex: 'page', key: 'page', render: (v: string) => <Text code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v}</Text> },
      { title: '标题', dataIndex: 'title', key: 'title', render: (v: string) => <Text style={{ color: 'var(--text-primary)' }}>{v}</Text> },
      { title: '类型', dataIndex: 'type', key: 'type', render: (v: string) => <Tag>{v}</Tag> },
      { title: 'Source数', dataIndex: 'source_count', key: 'source_count', render: () => <Tag color="error">0</Tag> },
    ]
    return <Table columns={columns} dataSource={items} rowKey="page" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  if (issueType === 'missing_concepts') {
    const columns = [
      { title: '概念', dataIndex: 'page', key: 'page', render: (v: string) => <Text code style={{ color: 'var(--accent)', fontSize: 12 }}>{v}</Text> },
      { title: '被引用次数', dataIndex: 'mentioned_count', key: 'mentioned_count', render: (v: number) => <Badge count={v} style={{ backgroundColor: '#1890ff' }} /> },
    ]
    return <Table columns={columns} dataSource={items} rowKey="page" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  if (issueType === 'quality_samples') {
    const columns = [
      { title: '页面', dataIndex: 'page', key: 'page', render: (v: string) => <Text code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v}</Text> },
      { title: '标题', dataIndex: 'title', key: 'title', render: (v: string) => <Text style={{ color: 'var(--text-primary)' }}>{v}</Text> },
      { title: '类型', dataIndex: 'type', key: 'type', render: (v: string) => <Tag>{v}</Tag> },
      { title: '质量分', dataIndex: 'quality_score', key: 'quality_score', render: (v: number) => <Text style={{ color: v >= 8 ? '#52c41a' : v >= 6 ? '#faad14' : '#ff4d4f', fontWeight: 700 }}>{v}/10</Text> },
      { title: '问题', dataIndex: 'quality_notes', key: 'quality_notes', render: (v: string[]) => v?.map((n: string) => <Tag key={n} color="warning" style={{ fontSize: 11, margin: 1 }}>{n}</Tag>) },
    ]
    return <Table columns={columns} dataSource={items} rowKey="page" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  if (issueType === 'llm_concept_suggestions') {
    const columns = [
      { title: '概念', dataIndex: 'concept', key: 'concept', render: (v: string) => <Text code style={{ color: 'var(--accent)', fontSize: 12 }}>{v}</Text> },
      { title: '被引用次数', dataIndex: 'mentioned_count', key: 'mentioned_count', render: (v: number) => <Badge count={v} style={{ backgroundColor: '#1890ff' }} /> },
      { title: '原因', dataIndex: 'reason', key: 'reason', render: (v: string) => <Text style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v}</Text> },
    ]
    return <Table columns={columns} dataSource={items} rowKey="concept" size="small" pagination={{ pageSize: 10, size: 'small' }} />
  }

  const columns = [
    { title: '页面', dataIndex: 'page', key: 'page', render: (v: string) => <Text code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{v}</Text> },
    { title: '标题', dataIndex: 'title', key: 'title', render: (v: string) => <Text style={{ color: 'var(--text-primary)' }}>{v || '-'}</Text> },
  ]
  return <Table columns={columns} dataSource={items} rowKey="page" size="small" pagination={{ pageSize: 10, size: 'small' }} />
}

export default function StatusPage() {
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [])

  const { data: status, refetch } = useQuery({
    queryKey: ['systemStatus'],
    queryFn: getSystemStatus,
    refetchInterval: 30000,
  })

  const [healthReport, setHealthReport] = useState<HealthCheckReport | null>(null)
  const [checkLayer, setCheckLayer] = useState<string>('layer1')
  const [fixLoading, setFixLoading] = useState<string | null>(null)

  const healthCheckMutation = useMutation({
    mutationFn: (layer: string) => runHealthCheck(layer),
    onSuccess: (data) => {
      setHealthReport(data)
    },
    onError: (error: Error) => {
      console.error('Health check failed:', error)
    },
  })

  const handleFix = async (action: string, data: Record<string, unknown>) => {
    try {
      if (action === 'fix_frontmatter') {
        const page = data.page as string
        if (!page) return
        setFixLoading(`frontmatter_${page}`)
        const result = await fixFrontmatter(page)
        if (result.success) {
          antMessage.success(result.message)
        } else {
          antMessage.error(result.message)
        }
      } else if (action === 'regenerate_paper') {
        const page = data.page as string
        if (!page) return
        setFixLoading(`regen_${page}`)
        try {
          const initResult = await regeneratePaper(page)
          if (initResult.status === 'failed') {
            antMessage.error(initResult.message)
            return
          }
          const taskId = initResult.task_id
          const deletedInfo = [
            initResult.deleted_paper ? `论文: ${initResult.deleted_paper}` : '',
            (initResult.deleted_entities as string[])?.length ? `实体: ${(initResult.deleted_entities as string[]).length}个` : '',
            (initResult.deleted_concepts as string[])?.length ? `概念: ${(initResult.deleted_concepts as string[]).length}个` : '',
          ].filter(Boolean).join('，')
          antMessage.info({ content: `论文已删除${deletedInfo ? '（' + deletedInfo + '）' : ''}，正在后台重新生成...`, key: 'regen', duration: 3 })
          const pollInterval = setInterval(async () => {
            try {
              const status = await getTaskStatus(taskId)
              if (status.status === 'completed') {
                clearInterval(pollInterval)
                pollingRef.current = null
                antMessage.success({ content: status.message, key: 'regen_done', duration: 5 })
                healthCheckMutation.mutate(checkLayer)
                setFixLoading(null)
              } else if (status.status === 'failed') {
                clearInterval(pollInterval)
                pollingRef.current = null
                antMessage.error({ content: status.message, key: 'regen_fail', duration: 8 })
                healthCheckMutation.mutate(checkLayer)
                setFixLoading(null)
              }
            } catch {
              // polling error, continue
            }
          }, 5000)
          pollingRef.current = pollInterval
        } catch (err: unknown) {
          const errorMsg = err instanceof Error ? err.message : '操作失败'
          antMessage.error(errorMsg)
        }
      } else if (action === 'remove_broken_links') {
        const page = data.page as string
        const brokenLinks = data.broken_links as string[]
        if (!page || !brokenLinks?.length) return
        setFixLoading(`link_${page}`)
        let removedCount = 0
        for (const link of brokenLinks) {
          try {
            const result = await fixBrokenLink(page, 'remove', link)
            if (result.success) removedCount++
          } catch {
            // skip individual failures
          }
        }
        antMessage.success(`已从 ${page} 删除 ${removedCount} 个断裂链接`)
      } else if (action === 'merge_entities') {
        const dupItems = data.items as Record<string, string>[]
        if (!dupItems || dupItems.length < 2) {
          antMessage.warning('至少需要2个重复项才能合并')
          return
        }
        showMergeModal(dupItems)
        return
      }

      healthCheckMutation.mutate(checkLayer)
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : '操作失败'
      antMessage.error(errorMsg)
    } finally {
      setFixLoading(null)
    }
  }

  const showMergeModal = (items: Record<string, string>[]) => {
    const options = items.map(item => ({
      label: `${item.title} (${item.type})`,
      value: item.page,
    }))

    let keepPage = options[0].value
    let removePage = options[1].value

    Modal.confirm({
      title: '合并重复实体',
      content: (
        <div style={{ paddingTop: 12 }}>
          <div style={{ marginBottom: 12 }}>
            <Text style={{ color: 'var(--text-secondary)', fontSize: 13 }}>保留的页面（合并后保留）：</Text>
            <Select
              style={{ width: '100%', marginTop: 4 }}
              defaultValue={keepPage}
              onChange={(v) => { keepPage = v }}
              options={options}
            />
          </div>
          <div>
            <Text style={{ color: 'var(--text-secondary)', fontSize: 13 }}>删除的页面（内容合并到保留页面）：</Text>
            <Select
              style={{ width: '100%', marginTop: 4 }}
              defaultValue={removePage}
              onChange={(v) => { removePage = v }}
              options={options}
            />
          </div>
        </div>
      ),
      okText: '确认合并',
      cancelText: '取消',
      onOk: async () => {
        if (keepPage === removePage) {
          antMessage.warning('保留页面和删除页面不能相同')
          return
        }
        try {
          const result = await mergeEntities(keepPage, removePage)
          if (result.success) {
            antMessage.success(result.message)
          } else {
            antMessage.error(result.message)
          }
          healthCheckMutation.mutate(checkLayer)
        } catch (err: unknown) {
          const errorMsg = err instanceof Error ? err.message : '合并失败'
          antMessage.error(errorMsg)
        }
      },
    })
  }

  const processedPct = status ? Math.round((status.processed_docs / status.total_docs) * 100) : 0
  const report = healthReport?.report
  const healthScore = report?.summary.health_score ?? 0
  const scoreColor = healthScore >= 90 ? '#52c41a' : healthScore >= 70 ? '#faad14' : '#ff4d4f'
  const details = report?.details || {}

  return (
    <div className="py-6 animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <Title level={2} style={{ color: 'var(--text-primary)', margin: 0 }}>
          <DashboardOutlined className="mr-2" style={{ color: 'var(--accent)' }} />
          系统状态
        </Title>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} className="btn-secondary">
          刷新
        </Button>
      </div>

      <Card className="glass-card-flat mb-6" title={<span style={{ color: 'var(--text-primary)' }}>📊 处理进度</span>}>
        <Row gutter={24}>
          <Col span={10}>
            <div className="flex justify-center">
              <Progress type="circle" percent={processedPct} size={180}
                strokeColor={{ '0%': 'var(--accent)', '100%': 'var(--success)' }}
                trailColor="var(--border)" />
            </div>
          </Col>
          <Col span={14}>
            <div className="space-y-6">
              <div className="status-card">
                <div className="value">{status?.total_docs || 0}</div>
                <div className="label">总文档</div>
              </div>
              <Row gutter={16}>
                <Col span={12}>
                  <div className="status-card">
                    <div className="value" style={{ color: 'var(--success)' }}>{status?.processed_docs || 0}</div>
                    <div className="label">已处理</div>
                  </div>
                </Col>
                <Col span={12}>
                  <div className="status-card">
                    <div className="value" style={{ color: 'var(--warning)' }}>{status?.pending_docs || 0}</div>
                    <div className="label">待处理</div>
                  </div>
                </Col>
              </Row>
            </div>
          </Col>
        </Row>
      </Card>

      <Row gutter={24} className="mb-6">
        <Col span={8}>
          <Card className="glass-card-flat">
            <Statistic title={<span style={{ color: 'var(--text-secondary)' }}>审核通过率</span>}
              value={status?.pass_rate || 0} suffix="%"
              prefix={status?.pass_rate && status.pass_rate >= 90 ? <CheckCircleOutlined style={{ color: 'var(--success)' }} /> : <WarningOutlined style={{ color: 'var(--warning)' }} />}
              valueStyle={{ color: status?.pass_rate && status.pass_rate >= 90 ? 'var(--success)' : 'var(--warning)', fontWeight: 700 }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card className="glass-card-flat">
            <Statistic title={<span style={{ color: 'var(--text-secondary)' }}>平均评分</span>}
              value={status?.avg_score || 0} suffix="/ 10" precision={1}
              valueStyle={{ color: 'var(--accent)', fontWeight: 700 }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card className="glass-card-flat">
            <Statistic title={<span style={{ color: 'var(--text-secondary)' }}>人工审核队列</span>}
              value={status?.review_queue || 0}
              prefix={status?.review_queue && status.review_queue > 0 ? <WarningOutlined style={{ color: 'var(--warning)' }} /> : <CheckCircleOutlined style={{ color: 'var(--success)' }} />}
              valueStyle={{ color: status?.review_queue && status.review_queue > 0 ? 'var(--warning)' : 'var(--success)', fontWeight: 700 }} />
          </Card>
        </Col>
      </Row>

      <Card className="glass-card-flat" title={<span style={{ color: 'var(--text-primary)' }}>🔍 系统健康体检</span>}>
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          {healthCheckMutation.isPending ? (
            <Tag color="processing" style={{ borderRadius: 9999, padding: '4px 12px' }}>
              <SyncOutlined spin className="mr-1" /> 正在体检...
            </Tag>
          ) : report ? (
            <Tag color={healthScore >= 90 ? 'success' : healthScore >= 70 ? 'warning' : 'error'}
              style={{ borderRadius: 9999, padding: '4px 12px' }}>
              {healthScore >= 90 ? <CheckCircleOutlined className="mr-1" /> :
               healthScore >= 70 ? <WarningOutlined className="mr-1" /> :
               <BugOutlined className="mr-1" />}
              健康分数 {healthScore}/100
            </Tag>
          ) : (
            <Tag color="default" style={{ borderRadius: 9999, padding: '4px 12px' }}>
              <MedicineBoxOutlined className="mr-1" /> 尚未体检
            </Tag>
          )}
          {report && (
            <Text style={{ color: 'var(--text-muted)' }}>
              上次体检: {report.timestamp}
            </Text>
          )}
        </div>

        <Divider style={{ margin: '16px 0', borderColor: 'var(--border)' }} />

        <div className="flex items-center gap-3 mb-4">
          <Segmented
            value={checkLayer}
            onChange={(v) => setCheckLayer(v as string)}
            options={[
              { label: '第一层：快速体检', value: 'layer1' },
              { label: '第二层：深度体检', value: 'layer2' },
              { label: '全部检查', value: 'all' },
            ]}
          />
          <Button type="primary" icon={<MedicineBoxOutlined />}
            onClick={() => healthCheckMutation.mutate(checkLayer)}
            loading={healthCheckMutation.isPending}>
            运行新体检
          </Button>
        </div>

        {healthCheckMutation.isPending && (
          <div className="flex flex-col items-center py-12">
            <Spin size="large" />
            <Text style={{ color: 'var(--text-muted)', marginTop: 16 }}>正在扫描知识库，请稍候...</Text>
          </div>
        )}

        {report && !healthCheckMutation.isPending && (
          <>
            <Row gutter={24} className="mb-6">
              <Col span={8}>
                <div className="flex justify-center">
                  <Progress type="circle" percent={healthScore} size={160}
                    strokeColor={scoreColor} trailColor="var(--border)"
                    format={(pct) => <span style={{ fontSize: 32, fontWeight: 700, color: scoreColor }}>{pct}</span>} />
                </div>
                <div className="text-center mt-2">
                  <Text style={{ color: 'var(--text-secondary)' }}>健康分数</Text>
                </div>
              </Col>
              <Col span={16}>
                <Row gutter={[16, 16]}>
                  {[
                    { name: '孤儿页面', key: 'orphans', weight: '15%' },
                    { name: '矛盾标记', key: 'conflicts', weight: '10%' },
                    { name: 'Frontmatter', key: 'invalid_frontmatter', weight: '10%' },
                    { name: '论文完整性', key: 'broken_papers', weight: '15%' },
                    { name: '交叉引用', key: 'broken_links', weight: '15%' },
                    { name: '重复实体', key: 'duplicate_entities', weight: '10%' },
                    { name: '无Source', key: 'no_source_id', weight: '10%' },
                  ].map(dim => {
                    const total = report.summary.total_pages || 1
                    const count = report.stats[dim.key] || 0
                    const score = Math.round((1 - count / total) * 100)
                    const dimColor = score >= 90 ? '#52c41a' : score >= 70 ? '#faad14' : '#ff4d4f'
                    return (
                      <Col span={6} key={dim.key}>
                        <Card size="small" className="glass-card-flat">
                          <div className="flex items-center justify-between">
                            <div>
                              <Text style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{dim.name}</Text>
                              <div style={{ fontSize: 18, fontWeight: 700, color: dimColor }}>{score}%</div>
                            </div>
                            <div className="text-right">
                              <Text style={{ color: 'var(--text-muted)', fontSize: 11 }}>权重 {dim.weight}</Text>
                              <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{count} 个问题</div>
                            </div>
                          </div>
                          <Progress percent={score} showInfo={false} size="small"
                            strokeColor={dimColor} trailColor="var(--border)" />
                        </Card>
                      </Col>
                    )
                  })}
                </Row>
              </Col>
            </Row>

            <Row gutter={16} className="mb-6">
              {[
                { label: '总页面', value: report.summary.total_pages },
                { label: '孤儿页面', value: report.stats.orphans || 0 },
                { label: '矛盾标记', value: report.stats.conflicts || 0 },
                { label: '无效FM', value: report.stats.invalid_frontmatter || 0 },
                { label: '不完整论文', value: report.stats.broken_papers || 0 },
                { label: '断裂链接', value: report.stats.broken_links || 0 },
                { label: '重复实体', value: report.stats.duplicate_entities || 0 },
                { label: '缺失概念', value: report.stats.missing_concepts || 0 },
                { label: '无Source', value: report.stats.no_source_id || 0 },
              ].map(s => (
                <Col flex={1} key={s.label}>
                  <Statistic title={<span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{s.label}</span>}
                    value={s.value} valueStyle={{ color: 'var(--text-primary)', fontSize: 18, fontWeight: 600 }} />
                </Col>
              ))}
            </Row>

            {report.issues.length > 0 && (
              <Collapse
                defaultActiveKey={report.issues.filter(i => i.severity !== 'info').map((_, i) => String(i))}
                style={{ background: 'var(--bg-secondary)', border: 'none' }}>
                {report.issues.map((issue, idx) => {
                  const config = severityConfig[issue.severity] || severityConfig.info
                  const issueDetails = details[issue.type] as unknown[] | undefined
                  return (
                    <Collapse.Panel
                      key={String(idx)}
                      header={
                        <Space>
                          {config.icon}
                          <Text style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                            {issueTypeLabels[issue.type] || issue.type}
                          </Text>
                          <Tag color={config.tagColor}>{config.label}</Tag>
                          {issue.count !== undefined && (
                            <Badge count={issue.count} style={{ backgroundColor: config.color }} />
                          )}
                        </Space>
                      }
                      style={{ background: 'var(--bg-primary)', marginBottom: 4, borderRadius: 8 }}
                    >
                      <Text style={{ color: 'var(--text-muted)', fontSize: 12, display: 'block', marginBottom: 12 }}>
                        {issueTypeDesc[issue.type] || issue.message || ''}
                      </Text>
                      {issueDetails && issueDetails.length > 0 ? (
                        <DetailTable issueType={issue.type} details={issueDetails} onFix={handleFix} />
                      ) : issue.pages && issue.pages.length > 0 ? (
                        <List size="small" dataSource={issue.pages}
                          renderItem={(page: string) => (
                            <List.Item style={{ border: 'none', padding: '4px 0' }}>
                              <Text code style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{page}</Text>
                            </List.Item>
                          )} />
                      ) : null}
                      {issue.threshold !== undefined && (
                        <Text style={{ color: 'var(--text-muted)', fontSize: 12, display: 'block', marginTop: 8 }}>
                          阈值: {issue.threshold * 100}%
                        </Text>
                      )}
                    </Collapse.Panel>
                  )
                })}
              </Collapse>
            )}
          </>
        )}

        {!report && !healthCheckMutation.isPending && (
          <Empty description='点击"运行新体检"开始检查知识库健康状况'
            image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
    </div>
  )
}
