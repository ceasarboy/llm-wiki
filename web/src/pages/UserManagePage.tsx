import { useState } from 'react'
import { Table, Card, Tag, Button, Select, Input, Modal, Typography, message, Space } from 'antd'
import { SearchOutlined, UserOutlined, KeyOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getUsers, updateUserRole, updateUserStatus, resetUserPassword } from '../services/authApi'
import type { User } from '../stores/useAuthStore'
import { formatDateTime } from '../utils/datetime'

const { Title } = Typography

const roleNames: Record<string, string> = {
  admin: '管理员',
  maintainer: '系统维护',
  core: '核心用户',
  general: '一般用户',
}

export default function UserManagePage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [roleFilter, setRoleFilter] = useState<string>()
  const [search, setSearch] = useState('')

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['users', page, pageSize, roleFilter, search],
    queryFn: () => getUsers({ page, page_size: pageSize, role: roleFilter, search }),
    retry: 1,
  })

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) =>
      updateUserRole(userId, role),
    onSuccess: () => {
      message.success('角色更新成功')
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: () => {
      message.error('角色更新失败')
    },
  })

  const statusMutation = useMutation({
    mutationFn: ({ userId, isActive }: { userId: number; isActive: boolean }) =>
      updateUserStatus(userId, isActive),
    onSuccess: () => {
      message.success('状态更新成功')
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: () => {
      message.error('状态更新失败')
    },
  })

  const resetPasswordMutation = useMutation({
    mutationFn: (userId: number) => resetUserPassword(userId),
    onSuccess: (data) => {
      message.success(data.message || '密码已重置为默认密码: 123456')
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: () => {
      message.error('密码重置失败')
    },
  })

  const handleRoleChange = (userId: number, role: string) => {
    Modal.confirm({
      title: '确认修改角色',
      content: `确定要将该用户的角色修改为"${roleNames[role]}"吗？`,
      onOk: () => roleMutation.mutate({ userId, role }),
    })
  }

  const handleStatusChange = (user: User) => {
    Modal.confirm({
      title: user.is_active ? '禁用用户' : '启用用户',
      content: user.is_active
        ? '确定要禁用该用户吗？禁用后用户将无法登录。'
        : '确定要启用该用户吗？',
      onOk: () => statusMutation.mutate({ userId: user.id, isActive: !user.is_active }),
    })
  }

  const handleResetPassword = (user: User) => {
    Modal.confirm({
      title: '重置密码',
      content: `确定要将用户 "${user.username}" 的密码重置为默认密码 "123456" 吗？`,
      okText: '确认重置',
      okButtonProps: { danger: true },
      onOk: () => resetPasswordMutation.mutate(user.id),
    })
  }

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      render: (text: string) => (
        <span className="flex items-center gap-2">
          <UserOutlined style={{ color: 'var(--text-muted)' }} />
          {text}
        </span>
      ),
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string, record: User) => (
        <Select
          value={role}
          style={{ width: 120 }}
          onChange={(value) => handleRoleChange(record.id, value)}
          options={[
            { value: 'admin', label: '管理员' },
            { value: 'maintainer', label: '系统维护' },
            { value: 'core', label: '核心用户' },
            { value: 'general', label: '一般用户' },
          ]}
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'success' : 'error'}>
          {isActive ? '正常' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '注册时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => formatDateTime(date),
    },
    {
      title: '最后登录',
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      render: (date: string | null) =>
        formatDateTime(date),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: User) => (
        <Space>
          <Button
            type="link"
            icon={<KeyOutlined />}
            onClick={() => handleResetPassword(record)}
          >
            重置密码
          </Button>
          <Button
            type="link"
            danger={record.is_active}
            onClick={() => handleStatusChange(record)}
          >
            {record.is_active ? '禁用' : '启用'}
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="py-6 animate-fade-in">
      <Title level={2} style={{ color: 'var(--text-primary)', marginBottom: 24 }}>
        <UserOutlined className="mr-2" style={{ color: 'var(--accent)' }} />
        用户管理
      </Title>

      <Card className="glass-card-flat">
        {isError && (
          <div style={{ padding: 16, marginBottom: 16, background: 'var(--error-light)', border: '1px solid var(--error)', borderRadius: 8 }}>
            <span style={{ color: 'var(--error)' }}>加载失败：{error instanceof Error ? error.message : '未知错误'}，请刷新页面重试</span>
          </div>
        )}
        <div className="mb-4 flex gap-4">
          <Select
            placeholder="角色筛选"
            allowClear
            style={{ width: 150 }}
            onChange={setRoleFilter}
            options={[
              { value: 'admin', label: '管理员' },
              { value: 'maintainer', label: '系统维护' },
              { value: 'core', label: '核心用户' },
              { value: 'general', label: '一般用户' },
            ]}
          />
          <Input.Search
            placeholder="搜索用户名或邮箱"
            allowClear
            style={{ width: 300 }}
            onSearch={setSearch}
            enterButton={<SearchOutlined />}
          />
        </div>

        <Table
          columns={columns}
          dataSource={data?.items}
          rowKey="id"
          loading={isLoading}
          pagination={{
            current: page,
            pageSize,
            total: data?.total,
            showSizeChanger: true,
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
