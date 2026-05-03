import { useState } from 'react'
import { Table, Card, Tabs, Tag, Input, Typography, Checkbox, Select, Space } from 'antd'
import { SearchOutlined, FileTextOutlined, ToolOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import request from '../services/api'
import { formatDateTime } from '../utils/datetime'

const { Title } = Typography

interface UserLogItem {
  id: number
  user_id: number
  username: string
  action: string
  resource_type: string | null
  resource_id: string | null
  details: string | null
  ip_address: string | null
  created_at: string
}

interface SystemLogItem {
  id: number
  level: string
  module: string
  action: string
  message: string | null
  details: string | null
  created_at: string
}

interface UserLogResponse {
  total: number
  page: number
  page_size: number
  items: UserLogItem[]
}

interface SystemLogResponse {
  total: number
  page: number
  page_size: number
  items: SystemLogItem[]
}

const levelOptions = [
  { label: 'INFO', value: 'INFO', color: 'blue' },
  { label: 'WARNING', value: 'WARNING', color: 'orange' },
  { label: 'ERROR', value: 'ERROR', color: 'red' },
]

export default function LogManagePage() {
  const [activeTab, setActiveTab] = useState('user')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [search, setSearch] = useState('')
  const [levelFilter, setLevelFilter] = useState<string[]>([])
  const [moduleFilter, setModuleFilter] = useState<string>()

  const { data: userLogs, isLoading: loadingUserLogs, isError: isUserLogError, error: userLogError } = useQuery({
    queryKey: ['userLogs', page, pageSize, search],
    queryFn: () =>
      request<UserLogResponse>(`/logs/user?page=${page}&page_size=${pageSize}${search ? `&keyword=${search}` : ''}`),
    enabled: activeTab === 'user',
    retry: 1,
  })

  const buildSystemLogUrl = () => {
    const params = new URLSearchParams()
    params.set('page', page.toString())
    params.set('page_size', pageSize.toString())
    if (search) params.set('keyword', search)
    if (levelFilter.length > 0) params.set('level', levelFilter.join(','))
    if (moduleFilter) params.set('module', moduleFilter)
    return `/logs/system?${params.toString()}`
  }

  const { data: systemLogs, isLoading: loadingSystemLogs, isError: isSystemLogError, error: systemLogError } = useQuery({
    queryKey: ['systemLogs', page, pageSize, search, levelFilter, moduleFilter],
    queryFn: () => request<SystemLogResponse>(buildSystemLogUrl()),
    enabled: activeTab === 'system',
    retry: 1,
  })

  const actionColors: Record<string, string> = {
    login: 'green',
    logout: 'default',
    query: 'blue',
    view_entity: 'cyan',
    view_concept: 'purple',
    edit_entity: 'orange',
    edit_concept: 'orange',
  }

  const levelColors: Record<string, string> = {
    INFO: 'blue',
    WARNING: 'orange',
    ERROR: 'red',
  }

  const moduleOptions = [...new Set(systemLogs?.items?.map(item => item.module) || [])].map(m => ({
    label: m,
    value: m,
  }))

  const userLogColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '用户',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      render: (action: string) => (
        <Tag color={actionColors[action] || 'default'}>{action}</Tag>
      ),
    },
    {
      title: '资源类型',
      dataIndex: 'resource_type',
      key: 'resource_type',
      render: (type: string) => type || '-',
    },
    {
      title: 'IP 地址',
      dataIndex: 'ip_address',
      key: 'ip_address',
      render: (ip: string) => ip || '-',
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => formatDateTime(date),
    },
  ]

  const systemLogColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 90,
      render: (level: string) => (
        <Tag color={levelColors[level] || 'default'}>{level}</Tag>
      ),
    },
    {
      title: '模块',
      dataIndex: 'module',
      key: 'module',
      width: 100,
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 130,
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => formatDateTime(date),
    },
  ]

  const handleLevelChange = (checkedValues: string[]) => {
    setLevelFilter(checkedValues)
    setPage(1)
  }

  const tabItems = [
    {
      key: 'user',
      label: (
        <span>
          <FileTextOutlined className="mr-1" />
          用户操作日志
        </span>
      ),
      children: (
        <Table
          columns={userLogColumns}
          dataSource={userLogs?.items}
          rowKey="id"
          loading={loadingUserLogs}
          pagination={{
            current: page,
            pageSize,
            total: userLogs?.total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      ),
    },
    {
      key: 'system',
      label: (
        <span>
          <ToolOutlined className="mr-1" />
          系统运行日志
        </span>
      ),
      children: (
        <>
          <div className="mb-4 flex items-center gap-6 flex-wrap">
            <div className="flex items-center gap-2">
              <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>级别筛选：</span>
              <Checkbox.Group
                options={levelOptions.map(opt => ({
                  label: <Tag color={opt.color}>{opt.label}</Tag>,
                  value: opt.value,
                }))}
                value={levelFilter}
                onChange={handleLevelChange}
              />
            </div>
            <div className="flex items-center gap-2">
              <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>模块：</span>
              <Select
                placeholder="全部模块"
                allowClear
                style={{ width: 150 }}
                value={moduleFilter}
                onChange={(val) => { setModuleFilter(val); setPage(1) }}
                options={moduleOptions}
              />
            </div>
          </div>
          <Table
            columns={systemLogColumns}
            dataSource={systemLogs?.items}
            rowKey="id"
            loading={loadingSystemLogs}
            pagination={{
              current: page,
              pageSize,
              total: systemLogs?.total,
              showSizeChanger: true,
              onChange: (p, ps) => {
                setPage(p)
                setPageSize(ps)
              },
            }}
          />
        </>
      ),
    },
  ]

  return (
    <div className="py-6 animate-fade-in">
      <Title level={2} style={{ color: 'var(--text-primary)', marginBottom: 24 }}>
        <FileTextOutlined className="mr-2" style={{ color: 'var(--accent)' }} />
        日志管理
      </Title>

      <Card className="glass-card-flat">
        {(isUserLogError || isSystemLogError) && (
          <div style={{ padding: 16, marginBottom: 16, background: 'var(--error-light)', border: '1px solid var(--error)', borderRadius: 8 }}>
            <span style={{ color: 'var(--error)' }}>
              加载失败：{(isUserLogError ? userLogError : systemLogError) instanceof Error ? (isUserLogError ? userLogError : systemLogError)?.message : '未知错误'}，请刷新页面重试
            </span>
          </div>
        )}
        <div className="mb-4">
          <Space>
            <Input.Search
              placeholder="搜索日志内容..."
              allowClear
              style={{ width: 300 }}
              onSearch={(val) => { setSearch(val); setPage(1) }}
              enterButton={<SearchOutlined />}
            />
          </Space>
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            setActiveTab(key)
            setPage(1)
          }}
          items={tabItems}
        />
      </Card>
    </div>
  )
}
