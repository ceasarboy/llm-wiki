import { useState } from 'react'
import { Card, Upload, Table, Button, message, Space, Tag, Modal, Typography } from 'antd'
import { UploadOutlined, DeleteOutlined, FilePdfOutlined, SyncOutlined, EyeOutlined } from '@ant-design/icons'
import { useQuery, useMutation } from '@tanstack/react-query'
import { uploadPDF, getPDFList, convertPDF, deletePDF } from '../services/api'
import type { PDFFile } from '../services/api'
import { formatDateTime } from '../utils/datetime'

const { Dragger } = Upload
const { Title } = Typography

export default function ImportPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['pdfList', page, pageSize],
    queryFn: () => getPDFList(page, pageSize),
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadPDF(file),
    onSuccess: () => {
      message.success('上传成功')
      refetch()
    },
    onError: (error: Error) => {
      message.error(`上传失败: ${error.message}`)
    },
  })

  const convertMutation = useMutation({
    mutationFn: (filename: string) => convertPDF(filename),
    onSuccess: () => {
      message.success('转换任务已启动')
      refetch()
    },
    onError: (error: Error) => {
      message.error(`转换失败: ${error.message}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (filename: string) => deletePDF(filename),
    onSuccess: () => {
      message.success('删除成功')
      refetch()
    },
    onError: (error: Error) => {
      message.error(`删除失败: ${error.message}`)
    },
  })

  const handleUpload = (file: File) => {
    uploadMutation.mutate(file)
    return false
  }

  const handleConvert = (filename: string) => {
    Modal.confirm({
      title: '确认转换',
      content: `确定要将 ${filename} 转换为Markdown吗？`,
      onOk: () => convertMutation.mutate(filename),
    })
  }

  const handleDelete = (filename: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 ${filename} 吗？`,
      okType: 'danger',
      onOk: () => deleteMutation.mutate(filename),
    })
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const statusColors: Record<string, string> = {
    pending: 'default',
    converting: 'processing',
    completed: 'success',
    failed: 'error',
  }

  const statusTexts: Record<string, string> = {
    pending: '待转换',
    converting: '转换中',
    completed: '已完成',
    failed: '转换失败',
  }

  const columns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      render: (text: string) => (
        <Space>
          <FilePdfOutlined />
          {text}
        </Space>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      render: (size: number) => formatSize(size),
    },
    {
      title: '上传时间',
      dataIndex: 'uploaded_at',
      key: 'uploaded_at',
      render: (text: string) => formatDateTime(text),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={statusColors[status]}>{statusTexts[status]}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: PDFFile) => (
        <Space>
          {record.status === 'pending' && (
            <Button
              icon={<SyncOutlined />}
              onClick={() => handleConvert(record.filename)}
              loading={convertMutation.isPending}
            >
              转换
            </Button>
          )}
          {record.status === 'converting' && (
            <Button disabled>
              转换中...
            </Button>
          )}
          {record.status === 'completed' && record.markdown_path && (
            <Button icon={<EyeOutlined />}>
              查看Markdown
            </Button>
          )}
          <Button
            icon={<DeleteOutlined />}
            danger
            onClick={() => handleDelete(record.filename)}
            loading={deleteMutation.isPending}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="max-w-6xl mx-auto py-6 animate-fade-in">
      <Title level={2} style={{ color: 'var(--text-primary)', marginBottom: 24 }}>
        <UploadOutlined className="mr-2" style={{ color: 'var(--accent)' }} />
        论文导入
      </Title>

      <Card className="glass-card-flat mb-6" title={<span style={{ color: 'var(--text-primary)' }}>📤 上传PDF</span>}>
        <Dragger
          accept=".pdf"
          beforeUpload={handleUpload}
          showUploadList={false}
          disabled={uploadMutation.isPending}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined style={{ color: 'var(--accent)', fontSize: 48 }} />
          </p>
          <p className="ant-upload-text" style={{ color: 'var(--text-primary)' }}>点击或拖拽文件到此区域上传PDF</p>
          <p className="ant-upload-hint" style={{ color: 'var(--text-secondary)' }}>支持单个文件上传，文件大小限制50MB</p>
        </Dragger>
      </Card>

      <Card className="glass-card-flat" title={<span style={{ color: 'var(--text-primary)' }}>📋 PDF列表</span>}>
        <Table
          columns={columns}
          dataSource={data?.items || []}
          rowKey="filename"
          loading={isLoading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: data?.total || 0,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      </Card>
    </div>
  )
}
