import { useState, useEffect } from 'react'
import { Input, List, Typography, Empty, Spin, Tag, Pagination, Tooltip } from 'antd'
import { FilePdfOutlined, SearchOutlined, ClockCircleOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { getPDFs } from '../services/api'

const { Text, Title } = Typography

export default function PDFReaderPage() {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selectedPdf, setSelectedPdf] = useState<string | null>(null)
  const pageSize = 50

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  const { data, isLoading } = useQuery({
    queryKey: ['pdfs', page, pageSize, debouncedSearch],
    queryFn: () => getPDFs(page, pageSize, debouncedSearch || undefined),
  })

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }

  return (
    <div className="h-[calc(100vh-64px)] flex">
      <div className="w-80 border-r border-[var(--border-color)] flex flex-col bg-[var(--bg-secondary)]">
        <div className="p-4 border-b border-[var(--border-color)]">
          <Title level={4} style={{ color: 'var(--text-primary)', marginBottom: 12 }}>
            <FilePdfOutlined className="mr-2" />
            PDF 文献库
          </Title>
          <Input
            placeholder="搜索PDF文件..."
            prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
          />
        </div>

        <div className="flex-1 overflow-auto">
          {isLoading ? (
            <div className="flex justify-center items-center h-32">
              <Spin />
            </div>
          ) : data?.items?.length === 0 ? (
            <Empty description="暂无PDF文件" className="mt-8" />
          ) : (
            <List
              dataSource={data?.items || []}
              renderItem={(item) => (
                <List.Item
                  className={`cursor-pointer px-4 py-3 hover:bg-[var(--bg-tertiary)] transition-fast ${
                    selectedPdf === item.id ? 'bg-[var(--bg-tertiary)] border-l-2 border-[var(--accent)]' : ''
                  }`}
                  onClick={() => setSelectedPdf(item.id)}
                  style={{ borderBottom: '1px solid var(--border-color)' }}
                >
                  <div className="w-full">
                    <div className="flex items-center gap-2 mb-1">
                      <FilePdfOutlined style={{ color: 'var(--error)' }} />
                      <Text
                        strong
                        style={{ color: 'var(--text-primary)', fontSize: 13 }}
                        className="truncate flex-1"
                      >
                        {item.title}
                      </Text>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <Tag color="blue" style={{ margin: 0 }}>{formatSize(item.size)}</Tag>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        <ClockCircleOutlined className="mr-1" />
                        {item.updated}
                      </Text>
                    </div>
                  </div>
                </List.Item>
              )}
            />
          )}
        </div>

        {data && data.total > pageSize && (
          <div className="p-3 border-t border-[var(--border-color)]">
            <Pagination
              simple
              current={page}
              pageSize={pageSize}
              total={data.total}
              onChange={setPage}
              size="small"
            />
          </div>
        )}

        <div className="p-3 border-t border-[var(--border-color)] bg-[var(--bg-primary)]">
          <Text type="secondary" style={{ fontSize: 12 }}>
            共 {data?.total || 0} 个PDF文件
          </Text>
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        {selectedPdf ? (
          <>
            <div className="p-3 border-b border-[var(--border-color)] bg-[var(--bg-secondary)] flex items-center justify-between">
              <Text strong style={{ color: 'var(--text-primary)' }}>
                <FilePdfOutlined className="mr-2" style={{ color: 'var(--error)' }} />
                {data?.items.find((item) => item.id === selectedPdf)?.title || selectedPdf}
              </Text>
              <Tooltip title="在新窗口打开">
                <a
                  href={`/api/pdf/serve/${encodeURIComponent(selectedPdf)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--accent)] hover:underline text-sm"
                >
                  新窗口打开
                </a>
              </Tooltip>
            </div>
            <div className="flex-1">
              <iframe
                src={`/api/pdf/serve/${encodeURIComponent(selectedPdf)}`}
                className="w-full h-full border-0"
                title="PDF Viewer"
              />
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <Empty
              image={<FilePdfOutlined style={{ fontSize: 64, color: 'var(--text-muted)' }} />}
              description={
                <Text type="secondary">从左侧列表选择PDF文件进行阅读</Text>
              }
            />
          </div>
        )}
      </div>
    </div>
  )
}
