import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { login } from '../services/authApi'
import { useAuthStore } from '../stores/useAuthStore'

const { Title, Text } = Typography

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((state) => state.setAuth)
  const [loading, setLoading] = useState(false)

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const response = await login(values)
      setAuth(response.access_token, response.user)
      message.success('登录成功')
      navigate('/')
    } catch (error: unknown) {
      const err = error as Error
      message.error(err.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: 'var(--bg-primary)' }}>
      <Card className="w-full max-w-md glass-card-flat">
        <div className="text-center mb-6">
          <Title level={2} style={{ color: 'var(--text-primary)', marginBottom: 8 }}>
            登录
          </Title>
          <Text style={{ color: 'var(--text-secondary)' }}>
            登录到 LLM-Wiki 知识库
          </Text>
        </div>

        <Form
          name="login"
          onFinish={onFinish}
          autoComplete="off"
          layout="vertical"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined style={{ color: 'var(--text-muted)' }} />}
              placeholder="用户名"
              size="large"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: 'var(--text-muted)' }} />}
              placeholder="密码"
              size="large"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              size="large"
            >
              登录
            </Button>
          </Form.Item>

          <div className="text-center">
            <Text style={{ color: 'var(--text-secondary)' }}>
              还没有账号？{' '}
              <Link to="/register" className="link">
                立即注册
              </Link>
            </Text>
          </div>
        </Form>
      </Card>
    </div>
  )
}
