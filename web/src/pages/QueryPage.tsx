import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Input, Card, Button, Tag, Spin, Empty, Typography, Divider, Space, message } from 'antd'
import { SendOutlined, SaveOutlined, CopyOutlined, LikeOutlined, DislikeOutlined } from '@ant-design/icons'
import { useAppStore } from '../stores/useAppStore'
import { postQuery } from '../services/api'
import { renderMarkdown } from '../utils/markdown'

const { Title, Text } = Typography

export default function QueryPage() {
  const { queryText } = useParams()
  const [inputValue, setInputValue] = useState('')
  const { queryResult, queryLoading, setQuery, setQueryResult, setQueryLoading } = useAppStore()

  useEffect(() => {
    if (queryText) {
      const decoded = decodeURIComponent(queryText)
      setQuery(decoded)
      setInputValue(decoded)
      doQuery(decoded)
    }
  }, [queryText])

  const doQuery = async (question: string) => {
    setQueryLoading(true)
    setQueryResult(null)
    try {
      const res = await postQuery(question)
      setQueryResult({
        question,
        answer: res.answer,
        sources: res.sources.map((s) => ({ id: s.id, title: s.title, path: s.path, relevance: s.relevance })),
        relatedQuestions: res.related_questions,
        timestamp: new Date().toISOString(),
      })
    } catch (err) {
      message.error('查询失败，请检查后端服务是否启动')
      console.error(err)
    } finally {
      setQueryLoading(false)
    }
  }

  const handleSend = () => {
    if (inputValue.trim()) {
      setQuery(inputValue.trim())
      doQuery(inputValue.trim())
    }
  }

  const handleSave = () => {
    message.success('已保存到 Wiki')
  }

  const handleCopy = () => {
    if (queryResult?.answer) {
      navigator.clipboard.writeText(queryResult.answer)
      message.success('已复制到剪贴板')
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-6">
      {/* 输入框 */}
      <div className="mb-8">
        <Input.TextArea
          size="large"
          placeholder="输入你的问题..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) { e.preventDefault(); handleSend() }
          }}
          autoSize={{ minRows: 2, maxRows: 4 }}
        />
        <div className="mt-3 text-right">
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={queryLoading}>
            查询
          </Button>
        </div>
      </div>

      {/* 加载中 */}
      {queryLoading && (
        <div className="text-center py-20">
          <Spin size="large" tip="正在检索知识库..." />
        </div>
      )}

      {/* 结果展示 */}
      {queryResult && !queryLoading && (
        <>
          {/* 问题 */}
          <Card className="mb-6" style={{ background: 'var(--bg-secondary)' }}>
            <Text type="secondary">你的问题：</Text>
            <Title level={4} style={{ color: 'var(--text-primary)', marginTop: 8, marginBottom: 0 }}>
              {queryResult.question}
            </Title>
          </Card>

          {/* 答案 */}
          <Card className="mb-6">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-2xl">🤖</span>
              <Text strong style={{ color: 'var(--text-primary)' }}>回答</Text>
            </div>
            <div
              className="markdown-content prose max-w-none"
              style={{ color: 'var(--text-primary)', lineHeight: 1.8 }}
              dangerouslySetInnerHTML={{ __html: renderMarkdown(queryResult.answer) }}
            />
            <Divider />
            {/* 来源 */}
            {queryResult.sources.length > 0 && (
              <div className="mb-4">
                <Text strong style={{ color: 'var(--text-primary)' }}>📚 来源：</Text>
                <div className="mt-2 space-y-1">
                  {queryResult.sources.map((src, i) => (
                    <div key={src.id} className="flex items-center gap-2">
                      <Tag color="blue">[{i + 1}]</Tag>
                      <Text className="cursor-pointer" style={{ color: 'var(--accent)' }}>{src.title}</Text>
                      <Text type="secondary" className="text-xs">{src.path}</Text>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* 操作按钮 */}
            <div className="flex gap-2 mt-4">
              <Button icon={<SaveOutlined />} onClick={handleSave}>保存到 Wiki</Button>
              <Button icon={<CopyOutlined />} onClick={handleCopy}>复制</Button>
              <Button icon={<LikeOutlined />}>有用</Button>
              <Button icon={<DislikeOutlined />}>无用</Button>
            </div>
          </Card>

          {/* 相关推荐 */}
          {queryResult.relatedQuestions.length > 0 && (
            <Card title="相关推荐">
              <Space direction="vertical" className="w-full">
                {queryResult.relatedQuestions.map((q, i) => (
                  <div
                    key={i}
                    className="cursor-pointer py-1"
                    style={{ color: 'var(--accent)' }}
                    onClick={() => { setInputValue(q); setQuery(q); doQuery(q) }}
                  >
                    <Text style={{ color: 'var(--accent)' }}>🔗 {q}</Text>
                  </div>
                ))}
              </Space>
            </Card>
          )}
        </>
      )}

      {/* 空状态 */}
      {!queryResult && !queryLoading && !queryText && (
        <div className="text-center py-20">
          <Empty description="输入问题开始查询" />
        </div>
      )}
    </div>
  )
}
