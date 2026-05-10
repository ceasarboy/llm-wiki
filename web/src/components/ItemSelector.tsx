import { useState, useEffect, useCallback } from 'react'
import { Input, Tag, List, Space, Segmented, Empty, Spin } from 'antd'
import { SearchOutlined, FileTextOutlined, BookOutlined, BulbOutlined, DatabaseOutlined } from '@ant-design/icons'
import { searchSynthesisItems } from '../services/api'

interface SelectedItem {
  id: string
  type: string
  title: string
}

export type { SelectedItem }

interface ItemResult {
  id: string
  title: string
  type: string
  tags: string[]
  updated: string
}

interface ItemSelectorProps {
  selected: SelectedItem[]
  onSelectedChange: (items: SelectedItem[]) => void
  minItems?: number
}

const TYPE_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  raw: { label: '原文', color: 'blue', icon: <DatabaseOutlined /> },
  paper: { label: '论文', color: 'purple', icon: <FileTextOutlined /> },
  entity: { label: '实体', color: 'green', icon: <BookOutlined /> },
  concept: { label: '概念', color: 'orange', icon: <BulbOutlined /> },
  synthesis: { label: '综合', color: 'cyan', icon: <FileTextOutlined /> },
}

const TYPE_FILTER_OPTIONS = [
  { label: '全部', value: '' },
  { label: '原文', value: 'raw' },
  { label: '论文', value: 'paper' },
  { label: '实体', value: 'entity' },
  { label: '概念', value: 'concept' },
]

export default function ItemSelector({ selected, onSelectedChange, minItems = 1 }: ItemSelectorProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [results, setResults] = useState<ItemResult[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)

  const selectedIds = new Set(selected.map(s => `${s.type}:${s.id}`))

  const doSearch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await searchSynthesisItems(searchQuery, typeFilter || undefined)
      setResults(res.items)
      setTotal(res.total)
    } catch {
      setResults([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [searchQuery, typeFilter])

  useEffect(() => {
    const timer = setTimeout(doSearch, 300)
    return () => clearTimeout(timer)
  }, [doSearch])

  useEffect(() => {
    doSearch()
  }, [])

  const handleToggle = (item: ItemResult) => {
    const key = `${item.type}:${item.id}`
    if (selectedIds.has(key)) {
      onSelectedChange(selected.filter(s => `${s.type}:${s.id}` !== key))
    } else {
      onSelectedChange([...selected, { id: item.id, type: item.type, title: item.title }])
    }
  }

  const handleRemove = (item: SelectedItem) => {
    onSelectedChange(selected.filter(s => !(s.id === item.id && s.type === item.type)))
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Space wrap style={{ marginBottom: 8 }}>
          <span style={{ fontWeight: 500 }}>已选 {selected.length} 项：</span>
          {selected.length === 0 && <span style={{ color: '#999' }}>请从下方列表中选择</span>}
          {selected.map(item => {
            const cfg = TYPE_CONFIG[item.type] || { label: item.type, color: 'default' }
            return (
              <Tag
                key={`${item.type}:${item.id}`}
                closable
                onClose={() => handleRemove(item)}
                color={cfg.color}
              >
                {cfg.label}: {item.title}
              </Tag>
            )
          })}
        </Space>
      </div>

      <Space style={{ marginBottom: 12, width: '100%' }} direction="vertical" size="small">
        <Input
          placeholder="搜索知识库项目..."
          prefix={<SearchOutlined />}
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          allowClear
        />
        <Segmented
          options={TYPE_FILTER_OPTIONS}
          value={typeFilter}
          onChange={v => setTypeFilter(v as string)}
          size="small"
        />
      </Space>

      <Spin spinning={loading}>
        <div style={{ maxHeight: 350, overflow: 'auto', border: '1px solid #f0f0f0', borderRadius: 6 }}>
          {results.length === 0 && !loading ? (
            <Empty description="未找到匹配项目" style={{ padding: 24 }} />
          ) : (
            <List
              dataSource={results}
              size="small"
              renderItem={(item) => {
                const key = `${item.type}:${item.id}`
                const isSelected = selectedIds.has(key)
                const cfg = TYPE_CONFIG[item.type] || { label: item.type, color: 'default', icon: <FileTextOutlined /> }
                return (
                  <List.Item
                    onClick={() => handleToggle(item)}
                    style={{
                      cursor: 'pointer',
                      padding: '8px 12px',
                      background: isSelected ? '#e6f7ff' : undefined,
                      borderLeft: isSelected ? '3px solid #1890ff' : '3px solid transparent',
                    }}
                  >
                    <List.Item.Meta
                      avatar={cfg.icon}
                      title={
                        <span style={{ fontSize: 13 }}>
                          {item.title}
                          {isSelected && <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>已选</Tag>}
                        </span>
                      }
                      description={
                        <Space size={4}>
                          <Tag color={cfg.color} style={{ fontSize: 11 }}>{cfg.label}</Tag>
                          {item.tags?.slice(0, 2).map(t => <Tag key={t} style={{ fontSize: 11 }}>{t}</Tag>)}
                          <span style={{ color: '#999', fontSize: 11 }}>{item.updated}</span>
                        </Space>
                      }
                    />
                  </List.Item>
                )
              }}
            />
          )}
        </div>
      </Spin>
      <div style={{ marginTop: 4, color: '#999', fontSize: 12 }}>
        共 {total} 个项目{typeFilter ? `（筛选: ${TYPE_CONFIG[typeFilter]?.label || typeFilter}）` : ''}
      </div>
    </div>
  )
}
