import { useState } from 'react'
import { Button, Card, Typography, Space, Progress, List, Tag, Input, Tabs, message } from 'antd'
import { FileTextOutlined, SwapOutlined, DownloadOutlined } from '@ant-design/icons'
import { createSurvey, createCompare, getSynthesisTask, listSyntheses, getPageDetail, exportSynthesisPdf } from '../services/api'
import { renderMarkdown } from '../utils/markdown'
import ItemSelector from '../components/ItemSelector'
import type { SelectedItem } from '../components/ItemSelector'

const { Title, Text, Paragraph } = Typography

function SurveyTab() {
  const [selectedItems, setSelectedItems] = useState<SelectedItem[]>([])
  const [topic, setTopic] = useState('')
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [taskStatus, setTaskStatus] = useState<Record<string, any> | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])

  const handleGenerate = async () => {
    if (selectedItems.length === 0) {
      message.warning('请至少选择 1 个项目')
      return
    }
    setLoading(true)
    setResult(null)
    setTaskStatus(null)
    try {
      const items = selectedItems.map(s => ({ id: s.id, type: s.type }))
      const res = await createSurvey(items, topic, prompt)
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
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong>综述主题（可选）</Text>
            <Input
              size="large"
              placeholder="例如：3D集成技术综述、Chiplet互连方案..."
              value={topic}
              onChange={e => setTopic(e.target.value)}
              style={{ marginTop: 8 }}
            />
          </div>
          <div>
            <Text strong>自定义提示词（可选）</Text>
            <Input.TextArea
              placeholder="补充对 LLM 的要求，例如：重点关注技术演进路线、用中文输出、增加应用场景分析..."
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              autoSize={{ minRows: 2, maxRows: 4 }}
              style={{ marginTop: 8 }}
            />
          </div>
          <div>
            <Text strong>选择知识库项目</Text>
            <div style={{ marginTop: 8 }}>
              <ItemSelector selected={selectedItems} onSelectedChange={setSelectedItems} minItems={1} />
            </div>
          </div>
          <Button type="primary" size="large" loading={loading} onClick={handleGenerate} icon={<FileTextOutlined />}>
            生成综述（已选 {selectedItems.length} 项）
          </Button>
        </Space>
      </Card>

      {taskStatus && loading && (
        <Card>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text>状态: {taskStatus.status === 'collecting' ? '收集内容...' : taskStatus.status === 'generating' ? '生成中...' : taskStatus.status === 'reviewing' ? '审核中...' : '保存中...'}</Text>
            <Progress percent={taskStatus.progress || 0} status="active" />
          </Space>
        </Card>
      )}

      {taskStatus && taskStatus.review_score !== undefined && (
        <Card>
          <Space>
            <Tag color={taskStatus.review_passed ? 'green' : 'orange'}>审核评分: {taskStatus.review_score?.toFixed(1)}</Tag>
            <Tag color={taskStatus.review_passed ? 'green' : 'red'}>{taskStatus.review_passed ? '通过' : '未通过（已保存草稿）'}</Tag>
          </Space>
        </Card>
      )}

      {result && (
        <Card title="综述结果">
          <div className="markdown-body" style={{ maxHeight: 600, overflow: 'auto' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(result) }} />
        </Card>
      )}

      <Card title="历史综述" extra={<Button size="small" onClick={loadHistory}>刷新</Button>}>
        <List
          dataSource={history}
          locale={{ emptyText: '暂无综述，点击刷新加载' }}
          renderItem={item => (
            <List.Item
              actions={[
                <Button key="export" type="link" size="small" icon={<DownloadOutlined />} onClick={() => exportSynthesisPdf(item.id)}>导出PDF</Button>
              ]}
            >
              <List.Item.Meta
                title={<a href={`/knowledge/synthesis/${item.id}`}>{item.title}</a>}
                description={<Space>{item.tags?.map((t: string) => <Tag key={t}>{t}</Tag>)}</Space>}
              />
              <Text type="secondary">{item.updated}</Text>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  )
}

function CompareTab() {
  const [selectedItems, setSelectedItems] = useState<SelectedItem[]>([])
  const [topic, setTopic] = useState('')
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [taskStatus, setTaskStatus] = useState<Record<string, any> | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])

  const handleGenerate = async () => {
    if (selectedItems.length < 2) {
      message.warning('至少需要选择 2 个项目进行对比')
      return
    }
    setLoading(true)
    setResult(null)
    setTaskStatus(null)
    try {
      const items = selectedItems.map(s => ({ id: s.id, type: s.type }))
      const res = await createCompare(items, topic, prompt)
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
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong>对比主题（可选）</Text>
            <Input
              size="large"
              placeholder="例如：Chiplet互连方案对比、3D集成 vs 2.5D..."
              value={topic}
              onChange={e => setTopic(e.target.value)}
              style={{ marginTop: 8 }}
            />
          </div>
          <div>
            <Text strong>自定义提示词（可选）</Text>
            <Input.TextArea
              placeholder="补充对 LLM 的要求，例如：重点关注性能差异、增加成本分析维度..."
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              autoSize={{ minRows: 2, maxRows: 4 }}
              style={{ marginTop: 8 }}
            />
          </div>
          <div>
            <Text strong>选择知识库项目（至少 2 个）</Text>
            <div style={{ marginTop: 8 }}>
              <ItemSelector selected={selectedItems} onSelectedChange={setSelectedItems} minItems={2} />
            </div>
          </div>
          <Button type="primary" size="large" loading={loading} onClick={handleGenerate} icon={<SwapOutlined />}>
            生成对比分析（已选 {selectedItems.length} 项）
          </Button>
        </Space>
      </Card>

      {taskStatus && loading && (
        <Card>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text>状态: {taskStatus.status === 'collecting' ? '收集内容...' : taskStatus.status === 'generating' ? '生成中...' : taskStatus.status === 'reviewing' ? '审核中...' : '保存中...'}</Text>
            <Progress percent={taskStatus.progress || 0} status="active" />
          </Space>
        </Card>
      )}

      {taskStatus && taskStatus.review_score !== undefined && (
        <Card>
          <Space>
            <Tag color={taskStatus.review_passed ? 'green' : 'orange'}>审核评分: {taskStatus.review_score?.toFixed(1)}</Tag>
            <Tag color={taskStatus.review_passed ? 'green' : 'red'}>{taskStatus.review_passed ? '通过' : '未通过（已保存草稿）'}</Tag>
          </Space>
        </Card>
      )}

      {result && (
        <Card title="对比结果">
          <div className="markdown-body" style={{ maxHeight: 600, overflow: 'auto' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(result) }} />
        </Card>
      )}

      <Card title="历史对比" extra={<Button size="small" onClick={loadHistory}>刷新</Button>}>
        <List
          dataSource={history}
          locale={{ emptyText: '暂无对比分析，点击刷新加载' }}
          renderItem={item => (
            <List.Item
              actions={[
                <Button key="export" type="link" size="small" icon={<DownloadOutlined />} onClick={() => exportSynthesisPdf(item.id)}>导出PDF</Button>
              ]}
            >
              <List.Item.Meta
                title={<a href={`/knowledge/synthesis/${item.id}`}>{item.title}</a>}
                description={<Space>{item.tags?.map((t: string) => <Tag key={t}>{t}</Tag>)}</Space>}
              />
              <Text type="secondary">{item.updated}</Text>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  )
}

export default function SurveyPage() {
  const [activeTab, setActiveTab] = useState('survey')

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <Title level={2}>🧠 智能分析</Title>
      <Paragraph type="secondary">
        从知识库中选择原文、论文、实体或概念，生成综述或对比分析。
      </Paragraph>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        size="large"
        items={[
          {
            key: 'survey',
            label: (
              <span>
                <FileTextOutlined style={{ marginRight: 6 }} />
                综述生成
              </span>
            ),
            children: <SurveyTab />,
          },
          {
            key: 'compare',
            label: (
              <span>
                <SwapOutlined style={{ marginRight: 6 }} />
                对比分析
              </span>
            ),
            children: <CompareTab />,
          },
        ]}
      />
    </div>
  )
}
