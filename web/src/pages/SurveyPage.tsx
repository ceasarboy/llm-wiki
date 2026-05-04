import { useState } from 'react'
import { Input, Button, Slider, Card, Typography, Space, Progress, List, Tag, message } from 'antd'
import { SearchOutlined, FileTextOutlined } from '@ant-design/icons'
import { createSurvey, getSynthesisTask, listSyntheses, getPageDetail } from '../services/api'
import { renderMarkdown } from '../utils/markdown'

const { Title, Text, Paragraph } = Typography

export default function SurveyPage() {
  const [keyword, setKeyword] = useState('')
  const [maxPapers, setMaxPapers] = useState(20)
  const [loading, setLoading] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<Record<string, any> | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])

  const handleGenerate = async () => {
    if (!keyword.trim()) {
      message.warning('请输入关键词')
      return
    }
    setLoading(true)
    setResult(null)
    setTaskStatus(null)
    try {
      const res = await createSurvey(keyword.trim(), maxPapers)
      setTaskId(res.task_id)
      pollTask(res.task_id)
    } catch (e: any) {
      message.error(e.message || '创建综述任务失败')
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
                setResult('综述已生成，请到知识库页面查看。')
              }
            }
          }
          message.success('综述生成完成！')
        } else if (status.status === 'failed') {
          clearInterval(interval)
          setLoading(false)
          message.error(`综述生成失败: ${status.error || '未知错误'}`)
        }
      } catch {
        clearInterval(interval)
        setLoading(false)
      }
    }, 3000)
  }

  const loadHistory = async () => {
    try {
      const res = await listSyntheses(1, 50, 'survey')
      setHistory(res.items)
    } catch {}
  }

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <Title level={2}>📚 综述生成</Title>
      <Paragraph type="secondary">
        输入一个技术方向或概念关键词，系统将自动检索相关论文并生成结构化综述。
      </Paragraph>

      <Card style={{ marginBottom: 24 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong>关键词</Text>
            <Input
              size="large"
              placeholder="例如：3D集成、Chiplet、知识蒸馏..."
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              onPressEnter={handleGenerate}
              prefix={<SearchOutlined />}
              style={{ marginTop: 8 }}
            />
          </div>
          <div>
            <Text strong>最大论文数: {maxPapers}</Text>
            <Slider min={5} max={50} value={maxPapers} onChange={setMaxPapers} style={{ marginTop: 8 }} />
          </div>
          <Button type="primary" size="large" loading={loading} onClick={handleGenerate} icon={<FileTextOutlined />}>
            生成综述
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
        <Card title="综述结果" style={{ marginBottom: 24 }}>
          <div className="markdown-body" style={{ maxHeight: 600, overflow: 'auto' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(result) }} />
        </Card>
      )}

      <Card title="历史综述" extra={<Button size="small" onClick={loadHistory}>刷新</Button>}>
        <List
          dataSource={history}
          locale={{ emptyText: '暂无综述，点击刷新加载' }}
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
