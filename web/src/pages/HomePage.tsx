import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Input, Card, Tag, Row, Col, Typography } from 'antd'
import { SearchOutlined, FireOutlined, ClockCircleOutlined, UserOutlined, BulbOutlined, FileTextOutlined, FolderOpenOutlined, BookOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { getHotQueries, getRecentUpdates } from '../services/api'

const { Title, Text } = Typography

const categories = [
  { key: 'entity', label: '实体', icon: <UserOutlined className="text-2xl" style={{ color: 'var(--accent)' }} />, color: 'var(--accent)' },
  { key: 'concept', label: '概念', icon: <BulbOutlined className="text-2xl" style={{ color: 'var(--purple)' }} />, color: 'var(--purple)' },
  { key: 'paper', label: '论文', icon: <FileTextOutlined className="text-2xl" style={{ color: 'var(--success)' }} />, color: 'var(--success)' },
  { key: 'synthesis', label: '综述', icon: <BookOutlined className="text-2xl" style={{ color: 'var(--orange)' }} />, color: 'var(--orange)' },
  { key: 'raw', label: '原文', icon: <FolderOpenOutlined className="text-2xl" style={{ color: 'var(--cyan)' }} />, color: 'var(--cyan)' },
]

const typeColors: Record<string, string> = {
  entity: 'blue',
  concept: 'purple',
  paper: 'green',
  summary: 'orange',
  synthesis: 'cyan',
  comparison: 'magenta',
  faq: 'gold',
  exploration: 'default',
}

export default function HomePage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')

  const { data: hotQueries, isLoading: loadingHot } = useQuery({
    queryKey: ['hotQueries'],
    queryFn: getHotQueries,
  })

  const { data: recentUpdates, isLoading: loadingRecent } = useQuery({
    queryKey: ['recentUpdates'],
    queryFn: () => getRecentUpdates(5),
  })

  const handleSearch = () => {
    if (query.trim()) {
      navigate(`/query/${encodeURIComponent(query.trim())}`)
    }
  }

  return (
    <div className="py-8 animate-fade-in">
      {/* Hero Section */}
      <div className="home-hero">
        <Title level={1} style={{ color: 'var(--text-primary)', marginBottom: 12, fontWeight: 700 }}>
          个人Wiki知识库
        </Title>
        <Text style={{ color: 'var(--text-secondary)', fontSize: 18, display: 'block', marginBottom: 32 }}>
          让知识沉淀、复用、迭代，构建高效、富有生命力的智能知识系统。
        </Text>
        
        {/* Search Box */}
        <div className="search-box">
          <Input.Search
            size="large"
            placeholder="输入问题或关键词搜索知识库..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onSearch={handleSearch}
            enterButton={<><SearchOutlined /> 搜索</>}
            style={{ borderRadius: 16 }}
          />
        </div>
      </div>

      {/* Quick Categories */}
      <div className="max-w-5xl mx-auto mb-12">
        <div className="flex justify-center gap-4 flex-wrap">
          {categories.map((cat) => (
            <div
              key={cat.key}
              className="category-card cursor-pointer"
              onClick={() => navigate(cat.key === 'raw' ? '/knowledge/raw' : `/knowledge/${cat.key}`)}
              role="button"
              tabIndex={0}
              aria-label={`浏览${cat.label}分类`}
              style={{ minWidth: 120 }}
            >
              <div className="icon">{cat.icon}</div>
              <Text strong style={{ color: 'var(--text-primary)' }}>{cat.label}</Text>
            </div>
          ))}
        </div>
      </div>

      {/* Hot Queries & Recent Updates */}
      <div style={{ maxWidth: 1024, margin: '0 auto' }}>
        <Row gutter={24} justify="center">
          <Col xs={24} sm={12}>
            <Card
              title={
                <span style={{ color: 'var(--text-primary)' }}>
                  <FireOutlined className="mr-2" style={{ color: 'var(--error)' }} />
                  热门查询
                </span>
              }
              loading={loadingHot}
              className="glass-card-flat"
            >
              {hotQueries?.queries?.map((q, i) => (
                <div
                  key={i}
                  className="py-3 px-3 cursor-pointer rounded-lg transition-fast hover:bg-tertiary"
                  onClick={() => navigate(`/query/${encodeURIComponent(q)}`)}
                  role="button"
                  tabIndex={0}
                >
                  <Text style={{ color: 'var(--text-primary)' }}>
                    <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>{i + 1}.</span>
                    {q}
                  </Text>
                </div>
              ))}
              {hotQueries?.saved?.length ? (
                <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--border)' }}>
                  <Text type="secondary" style={{ fontSize: 12, marginBottom: 8, display: 'block' }}>
                    📌 已保存的问答
                  </Text>
                  {hotQueries.saved.map((item, i) => (
                    <div
                      key={item.id || i}
                      className="py-2 px-3 cursor-pointer rounded-lg transition-fast hover:bg-tertiary"
                      onClick={() => navigate(`/knowledge/${encodeURIComponent(item.id)}`)}
                      role="button"
                      tabIndex={0}
                    >
                      <Text style={{ color: 'var(--accent)' }}>{item.question}</Text>
                    </div>
                  ))}
                </div>
              ) : null}
            </Card>
          </Col>
          <Col xs={24} sm={12}>
            <Card
              title={
                <span style={{ color: 'var(--text-primary)' }}>
                  <ClockCircleOutlined className="mr-2" style={{ color: 'var(--accent)' }} />
                  最新更新
                </span>
              }
              loading={loadingRecent}
              className="glass-card-flat"
            >
              {recentUpdates?.items?.map((item) => (
                <div key={item.id} className="py-3 px-3 flex items-center justify-between rounded-lg transition-fast hover:bg-tertiary cursor-pointer">
                  <Text 
                    className="cursor-pointer transition-fast" 
                    style={{ color: 'var(--text-primary)' }}
                    onClick={() => navigate(`/knowledge/${item.id}`)}
                  >
                    {item.title}
                  </Text>
                  <Tag color={typeColors[item.type] || 'default'}>{item.type}</Tag>
                </div>
              ))}
            </Card>
          </Col>
        </Row>
      </div>
    </div>
  )
}
