import { Card, Form, Input, Button, Typography, message, Spin, Divider, InputNumber, Row, Col } from 'antd'
import { SettingOutlined, FolderOutlined, DatabaseOutlined, RobotOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import request from '../services/api'

const { Title, Text } = Typography

interface LLMConfig {
  api_url: string
  model: string
  api_key: string
  temperature: number
  max_tokens: number
  timeout: number
}

interface SystemConfig {
  vault_root: string
  raw_dir: string
  wiki_dir: string
  work_dir: string
  index_dir: string
  llm: LLMConfig
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [form] = Form.useForm()

  const { data: config, isLoading } = useQuery({
    queryKey: ['systemConfig'],
    queryFn: () => request<SystemConfig>('/config'),
  })

  const updateMutation = useMutation({
    mutationFn: (values: Partial<SystemConfig>) =>
      request<{ success: boolean; message: string }>('/config', {
        method: 'PUT',
        body: JSON.stringify(values),
      }),
    onSuccess: () => {
      message.success('配置已更新，重启服务生效')
      queryClient.invalidateQueries({ queryKey: ['systemConfig'] })
    },
    onError: () => {
      message.error('更新失败')
    },
  })

  const onFinish = (values: any) => {
    const updateData: Partial<SystemConfig> = {
      vault_root: values.vault_root,
      raw_dir: values.raw_dir,
      wiki_dir: values.wiki_dir,
      llm: {
        api_url: values.api_url,
        model: values.model,
        api_key: values.api_key,
        temperature: values.temperature,
        max_tokens: values.max_tokens,
        timeout: values.timeout,
      },
    }
    updateMutation.mutate(updateData)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div className="py-6 animate-fade-in">
      <Title level={2} style={{ color: 'var(--text-primary)', marginBottom: 24 }}>
        <SettingOutlined className="mr-2" style={{ color: 'var(--accent)' }} />
        系统设置
      </Title>

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          vault_root: config?.vault_root,
          raw_dir: config?.raw_dir,
          wiki_dir: config?.wiki_dir,
          api_url: config?.llm?.api_url,
          model: config?.llm?.model,
          api_key: config?.llm?.api_key,
          temperature: config?.llm?.temperature,
          max_tokens: config?.llm?.max_tokens,
          timeout: config?.llm?.timeout,
        }}
        onFinish={onFinish}
      >
        <Card className="glass-card-flat mb-6" title={<span style={{ color: 'var(--text-primary)' }}><FolderOutlined className="mr-2" />Obsidian 目录配置</span>}>
          <Row gutter={24}>
            <Col span={24}>
              <Form.Item
                name="vault_root"
                label="Obsidian Vault 根目录"
                rules={[{ required: true, message: '请输入 Vault 根目录' }]}
              >
                <Input placeholder="C:/Users/xxx/Documents/Obsidian Vault" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="raw_dir"
                label="原始文档目录"
                rules={[{ required: true, message: '请输入原始文档目录' }]}
              >
                <Input placeholder="C:/Users/xxx/Documents/Obsidian Vault/raw/papers/markdown" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="wiki_dir"
                label="Wiki 输出目录"
                rules={[{ required: true, message: '请输入 Wiki 输出目录' }]}
              >
                <Input placeholder="C:/Users/xxx/Documents/Obsidian Vault/wiki" />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card className="glass-card-flat mb-6" title={<span style={{ color: 'var(--text-primary)' }}><RobotOutlined className="mr-2" />LLM 模型配置</span>}>
          <Row gutter={24}>
            <Col span={24}>
              <Form.Item
                name="api_url"
                label="API 地址"
                rules={[{ required: true, message: '请输入 API 地址' }]}
              >
                <Input placeholder="https://api.siliconflow.cn/v1/chat/completions" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="model"
                label="模型名称"
                rules={[{ required: true, message: '请输入模型名称' }]}
              >
                <Input placeholder="Pro/moonshotai/Kimi-K2.5" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="api_key"
                label="API Key"
              >
                <Input.Password placeholder="sk-xxx" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="temperature"
                label="Temperature"
                tooltip="控制输出随机性，0-1 之间，越低越确定"
              >
                <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="max_tokens"
                label="Max Tokens"
                tooltip="单次请求最大输出 token 数"
              >
                <InputNumber min={100} max={32768} step={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="timeout"
                label="超时时间 (秒)"
                tooltip="请求超时时间"
              >
                <InputNumber min={10} max={600} step={10} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card className="glass-card-flat mb-6" title={<span style={{ color: 'var(--text-primary)' }}><DatabaseOutlined className="mr-2" />系统目录配置（只读）</span>}>
          <Row gutter={24}>
            <Col span={12}>
              <div className="mb-4">
                <Text type="secondary">工作目录</Text>
                <div className="mt-1">
                  <Text strong style={{ color: 'var(--text-primary)' }}>{config?.work_dir}</Text>
                </div>
              </div>
            </Col>
            <Col span={12}>
              <div className="mb-4">
                <Text type="secondary">索引目录</Text>
                <div className="mt-1">
                  <Text strong style={{ color: 'var(--text-primary)' }}>{config?.index_dir}</Text>
                </div>
              </div>
            </Col>
          </Row>
        </Card>

        <Form.Item>
          <Button type="primary" htmlType="submit" loading={updateMutation.isPending} size="large">
            保存配置
          </Button>
        </Form.Item>

        <Divider />

        <Text type="secondary" style={{ fontSize: 12 }}>
          注意：修改配置后需要重启后端服务才能生效。
        </Text>
      </Form>
    </div>
  )
}
