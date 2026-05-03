import { useState, useEffect, useRef } from 'react'
import { Card, Table, Button, Typography, Space, message, Modal, InputNumber, Tag, Spin } from 'antd'
import { UploadOutlined, FileTextOutlined, SyncOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import request from '../services/api'
import { formatDateTime } from '../utils/datetime'

const { Title, Text } = Typography

interface PendingDoc {
  filename: string
  path: string
  size: number
  modified: string
}

interface PendingDocsResponse {
  count: number
  items: PendingDoc[]
}

interface IngestResult {
  success: boolean
  message: string
  processed: number
}

interface IngestLogResponse {
  log: string
  finished: boolean
}

export default function IngestPage() {
  const [limit, setLimit] = useState(10)
  const [ingesting, setIngesting] = useState(false)
  const [ingestMessage, setIngestMessage] = useState<string | null>(null)
  const [logContent, setLogContent] = useState<string>('')
  const logRef = useRef<HTMLPreElement>(null)
  const logIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['pendingDocs'],
    queryFn: () => request<PendingDocsResponse>('/ingest/pending'),
  })

  // 轮询日志
  const fetchLog = async () => {
    try {
      const result = await request<IngestLogResponse>('/ingest/log')
      setLogContent(result.log)
      if (result.finished && logIntervalRef.current) {
        clearInterval(logIntervalRef.current)
        logIntervalRef.current = null
        setIngesting(false)
        if (result.log.includes('导入完成')) {
          message.success('导入完成')
          refetch()
        }
      }
    } catch (error) {
      console.error('获取日志失败:', error)
    }
  }

  // 自动滚动到底部
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logContent])

  // 清理定时器
  useEffect(() => {
    return () => {
      if (logIntervalRef.current) {
        clearInterval(logIntervalRef.current)
      }
    }
  }, [])

  const handleIngest = async () => {
    Modal.confirm({
      title: '确认导入',
      content: `确定要导入 ${limit} 篇论文吗？这可能需要一些时间。`,
      onOk: async () => {
        setIngesting(true)
        setIngestMessage(null)
        setLogContent('')
        try {
          const result = await request<IngestResult>(`/ingest/run?limit=${limit}`, {
            method: 'POST',
          })
          if (result.success) {
            // 开始轮询日志
            logIntervalRef.current = setInterval(fetchLog, 2000)
            // 立即获取一次
            fetchLog()
          } else {
            message.error(result.message)
            setIngestMessage(result.message)
            setIngesting(false)
          }
        } catch (error: unknown) {
          const err = error as Error
          message.error(err.message || '导入失败')
          setIngesting(false)
        }
      },
    })
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const columns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      render: (text: string) => (
        <span className="flex items-center gap-2">
          <FileTextOutlined style={{ color: 'var(--accent)' }} />
          <Text ellipsis style={{ maxWidth: 300 }}>{text}</Text>
        </span>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 100,
      render: (size: number) => formatSize(size),
    },
    {
      title: '修改时间',
      dataIndex: 'modified',
      key: 'modified',
      width: 180,
      render: (date: string) => formatDateTime(date),
    },
  ]

  return (
    <div className="py-6 animate-fade-in">
      <Title level={2} style={{ color: 'var(--text-primary)', marginBottom: 24 }}>
        <UploadOutlined className="mr-2" style={{ color: 'var(--accent)' }} />
        论文导入
      </Title>

      <Card className="glass-card-flat mb-6">
        <div className="flex items-center justify-between mb-4">
          <Space>
            <Tag color="blue" style={{ fontSize: 14, padding: '4px 12px' }}>
              待处理: {data?.count || 0} 篇
            </Tag>
            <Button icon={<SyncOutlined />} onClick={() => refetch()}>
              刷新
            </Button>
          </Space>
          <Space>
            <Text>导入数量:</Text>
            <InputNumber
              min={1}
              max={100}
              value={limit}
              onChange={(v) => setLimit(v || 10)}
              style={{ width: 80 }}
            />
            <Button
              type="primary"
              icon={<UploadOutlined />}
              loading={ingesting}
              onClick={handleIngest}
              disabled={!data?.count}
            >
              开始导入
            </Button>
          </Space>
        </div>

        {ingestMessage && (
          <div className="mb-4 p-4 rounded-lg" style={{ background: 'var(--bg-tertiary)' }}>
            <pre style={{ whiteSpace: 'pre-wrap', color: 'var(--text-secondary)', margin: 0, fontSize: 12 }}>
              {ingestMessage}
            </pre>
          </div>
        )}

        {logContent && (
          <div className="mb-4 p-4 rounded-lg" style={{ background: 'var(--bg-tertiary)' }}>
            <div className="flex items-center justify-between mb-2">
              <Text strong style={{ color: 'var(--text-primary)' }}>导入日志</Text>
              {ingesting && <Spin size="small" />}
            </div>
            <pre 
              ref={logRef}
              style={{ 
                whiteSpace: 'pre-wrap', 
                color: 'var(--text-secondary)', 
                margin: 0, 
                fontSize: 11,
                maxHeight: 300,
                overflow: 'auto',
                background: 'var(--bg-secondary)',
                padding: 12,
                borderRadius: 8,
              }}
            >
              {logContent}
            </pre>
          </div>
        )}
      </Card>

      <Card className="glass-card-flat" title={<span style={{ color: 'var(--text-primary)' }}>待处理文档列表</span>}>
        <Spin spinning={isLoading}>
          <Table
            columns={columns}
            dataSource={data?.items}
            rowKey="filename"
            pagination={{ pageSize: 20, showSizeChanger: true }}
            locale={{ emptyText: '暂无待处理文档' }}
          />
        </Spin>
      </Card>
    </div>
  )
}
