import { useState } from 'react'
import { Input, Button, Card, Typography, Space, Progress, List, Tag, Segmented, message } from 'antd'
import { SwapOutlined, FileTextOutlined } from '@ant-design/icons'
import { createCompare, getSynthesisTask, listSyntheses, getPageDetail } from '../services/api'
import { renderMarkdown } from '../utils/markdown'

const { Title, Text, Paragraph } = Typography

export default function ComparePage() {
  const [mode, setMode] = useState<'papers' | 'concepts'>('concepts')
  const [items, setItems] = useState<string[]>(['', ''])
  const [maxPerConcept, setMaxPerConcept] = useState(5)
  const [loading, setLoading] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<Record<string, any> | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])

  const handleGenerate = async () => {
    const validItems = items.filter(i => i.trim())
    if (validItems.length < 2) {
      message.warning('至少需要 2 个对比项')
      return
    }
    setLoading(true)
    setResult(null)
    setTaskStatus(null)
    try {
      const res = await createCompare(mode, validItems, maxPerConcept)
      setTaskId(res.task_id)
      pollTask(res.task_id)
    } catch (e: any) {
      message.error(e.message || '创建对比任务失败')
      setLoading(false)
    }
  }

  const pollTask = (tid: string) => {
    const interval = setInterval(async () => {
      try {
        const status = await getSynthesisTask(tid)
        setTaskStatus(status)
        if (status.status === 'completed') {
          clearInterval(interval)
          setLoading(false)
          if (status.result_file) {
            const pageId = status.result_file.replace(/\\/g, '/').split('wiki/')[1]?.replace('.md', '') || ''
            if (pageId) {
              try {
                const detail = await getPageDetail(pageId)
                setResult(detail.content)
              } catch {
                setResult('对比分析已生成，请到知识库页面查看。')
              }
            }
          }
          message.success('对比分析完成！')
        } else if (status.status === 'failed') {
          clearInterval(interval)
          setLoading(false)
          message.error(`对比分析失败: ${status.error || '未知错误'}`)
        }
      } catch {
        clearInterval(interval)
        setLoading(false)
      }
    }, 3000)
  }

  const loadHistory = async () => {
    try {
      const res = await listSyntheses(1, 50, 'comparison')
      setHistory(res.items)
    } catch {}
  }

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <Title level={2}>⚖️ 对比分析</Title>
      <Paragraph type="secondary">
        选择多篇论文或多个概念，系统将自动生成对比矩阵和场景化建议。
      </Paragraph>

      <Card style={{ marginBottom: 24 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong>对比模式</Text>
            <div style={{ marginTop: 8 }}>
              <Segmented
                options={[
                  { label: '概念对比', value: 'concepts' },
                  { label: '论文对比', value: 'papers' },
                ]}
                value={mode}
                onChange={v => setMode(v as 'papers' | 'concepts')}
              />
            </div>
          </div>

          <div>
            <Text strong>{mode === 'concepts' ? '概念关键词' : '论文 ID/标题'}</Text>
            {items.map((item, idx) => (
              <Input
                key={idx}
                placeholder={mode === 'concepts' ? `概念 ${idx + 1}，如：Chiplet` : `论文 ${idx + 1} 的 ID 或标题`}
                value={item}
                onChange={e => {
                  const newItems = [...items]
                  newItems[idx] = e.target.value
                  setItems(newItems)
                }}
                style={{ marginTop: 8 }}
              />
            ))}
            <Button type="dashed" size="small" style={{ marginTop: 8 }} onClick={() => setItems([...items, ''])}>
              + 添加对比项
            </Button>
          </div>

          {mode === 'concepts' && (
            <div>
              <Text strong>每个概念最大论文数: {maxPerConcept}</Text>
            </div>
          )}

          <Button type="primary" size="large" loading={loading} onClick={handleGenerate} icon={<SwapOutlined />}>
            生成对比分析
          </Button>
        </Space>
      </Card>

      {taskStatus && loading && (
        <Card style={{ marginBottom: 24 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text>状态: {taskStatus.status === 'generating' ? '生成中...' : taskStatus.status === 'reviewing' ? '审核中...' : '保存中...'}</Text>
            <Progress percent={taskStatus.progress || 0} status="active" />
          </Space>
        </Card>
      )}

      {taskStatus && taskStatus.review_score !== undefined && (
        <Card style={{ marginBottom: 24 }}>
          <Space>
            <Tag color={taskStatus.review_passed ? 'green' : 'orange'}>
              审核评分: {taskStatus.review_score?.toFixed(1)}
            </Tag>
            <Tag color={taskStatus.review_passed ? 'green' : 'red'}>
              {taskStatus.review_passed ? '通过' : '未通过（已保存草稿）'}
            </Tag>
          </Space>
        </Card>
      )}

      {result && (
        <Card title="对比结果" style={{ marginBottom: 24 }}>
          <div className="markdown-body" style={{ maxHeight: 600, overflow: 'auto' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(result) }} />
        </Card>
      )}

      <Card title="历史对比" extra={<Button size="small" onClick={loadHistory}>刷新</Button>}>
        <List
          dataSource={history}
          locale={{ emptyText: '暂无对比分析，点击刷新加载' }}
          renderItem={item => (
            <List.Item>
              <List.Item.Meta
                title={<a href={`/knowledge/synthesis/${item.id}`}>{item.title}</a>}
                description={<Space>{item.tags?.map((t: string) => <Tag key={t}>{t}</Tag>)}</Space>}
              />
              <Text type="secondary">{item.updated}</Text>
            </List.Item>
          )}
        />
      </Card>
    </div>
  )
}
