import { useEffect, useRef, useState, useMemo } from 'react'
import { Card, Typography, Spin, Select, Input, Tag, Drawer, Descriptions, Statistic, Row, Col, Button, Space, Switch } from 'antd'
import { ApartmentOutlined, SearchOutlined, NodeIndexOutlined, ZoomInOutlined, ZoomOutOutlined, ReloadOutlined, FullscreenOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import request from '../services/api'
import cytoscape from 'cytoscape'
// @ts-ignore cytoscape-fcose has no types
import fcose from 'cytoscape-fcose'

cytoscape.use(fcose)

type CyCore = cytoscape.Core
type CyNodeSingular = cytoscape.NodeSingular
type CyLayoutOptions = cytoscape.LayoutOptions

const { Title, Text } = Typography

function getThemeColor(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
}

const typeColorVars: Record<string, string> = {
  paper: '--accent',
  entity: '--success',
  concept: '--warning',
  synthesis: '--orange',
  entitie: '--success',
}

function getTypeColor(type: string): string {
  const varName = typeColorVars[type]
  return varName ? getThemeColor(varName) : getThemeColor('--text-muted')
}

interface GraphNode {
  id: string
  label: string
  type: string
  tags: string[]
  path: string
}

interface GraphEdge {
  id: string
  source: string
  target: string
  type: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  metadata: {
    totalNodes: number
    totalEdges: number
    lastUpdated: string
  }
}

const typeNames: Record<string, string> = {
  paper: '论文',
  entity: '实体',
  concept: '概念',
  synthesis: '综述',
  entitie: '实体',
}

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<CyCore | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [filterType, setFilterType] = useState<string>('all')
  const [searchText, setSearchText] = useState('')
  const [nodeCount, setNodeCount] = useState(0)
  const [showConnectedOnly, setShowConnectedOnly] = useState(true)
  const [layoutStrength, setLayoutStrength] = useState<'normal' | 'spread'>('spread')

  const { data: graphData, isLoading } = useQuery({
    queryKey: ['graphData', filterType],
    queryFn: () => request<GraphData>(`/graph/data?type=${filterType}`),
  })

  const { data: stats } = useQuery({
    queryKey: ['graphStats'],
    queryFn: () => request<{ totalNodes: number; totalEdges: number; nodeTypes: Record<string, number> }>('/graph/stats'),
  })

  const filteredData = useMemo(() => {
    if (!graphData) return null
    
    if (!showConnectedOnly) {
      return graphData
    }
    
    const connectedNodeIds = new Set<string>()
    graphData.edges.forEach(edge => {
      connectedNodeIds.add(edge.source)
      connectedNodeIds.add(edge.target)
    })
    
    const filteredNodes = graphData.nodes.filter(node => connectedNodeIds.has(node.id))
    const filteredEdges = graphData.edges.filter(edge => 
      connectedNodeIds.has(edge.source) && connectedNodeIds.has(edge.target)
    )
    
    return {
      ...graphData,
      nodes: filteredNodes,
      edges: filteredEdges,
    }
  }, [graphData, showConnectedOnly])

  useEffect(() => {
    if (!filteredData || !containerRef.current) return

    const container = containerRef.current

    if (cyRef.current) {
      cyRef.current.destroy()
    }

    const nodeMap = new Map<string, GraphNode>()
    filteredData.nodes.forEach(n => nodeMap.set(n.id, n))

    const validEdges = filteredData.edges.filter(edge => 
      nodeMap.has(edge.source) && nodeMap.has(edge.target)
    )

    const connectionCount = new Map<string, number>()
    validEdges.forEach(edge => {
      connectionCount.set(edge.source, (connectionCount.get(edge.source) || 0) + 1)
      connectionCount.set(edge.target, (connectionCount.get(edge.target) || 0) + 1)
    })

    const layoutParams = layoutStrength === 'spread' ? {
      idealEdgeLength: 50,
      nodeRepulsion: 1000000,
      nodeSeparation: 300,
      nestingFactor: 0.01,
      gravity: 0.001,
      gravityRange: 0.1,
      tile: true,
      packComponents: true,
      samplingType: 1,
      samplingSize: 50,
      maxIterations: 3000,
      tilingPaddingVertical: 150,
      tilingPaddingHorizontal: 150,
    } : {
      idealEdgeLength: 80,
      nodeRepulsion: 500000,
      nodeSeparation: 200,
      nestingFactor: 0.05,
      gravity: 0.005,
      gravityRange: 0.5,
      tile: true,
      packComponents: true,
      samplingType: 1,
      samplingSize: 30,
      maxIterations: 2000,
      tilingPaddingVertical: 100,
      tilingPaddingHorizontal: 100,
    }

    const cy = cytoscape({
      container,
      elements: {
        nodes: filteredData.nodes.map(node => {
          const connections = connectionCount.get(node.id) || 0
          const size = 25 + Math.min(connections * 3, 25)
          return {
            data: {
              id: node.id,
              label: node.label.length > 12 ? node.label.substring(0, 12) + '...' : node.label,
              fullLabel: node.label,
              type: node.type,
              tags: node.tags,
              path: node.path,
              connections,
              size,
            },
          }
        }),
        edges: validEdges.map(edge => ({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
          },
        })),
      },
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (ele: CyNodeSingular) => getTypeColor(ele.data('type')),
            'label': 'data(label)',
            'width': 'data(size)',
            'height': 'data(size)',
            'font-size': '9px',
            'color': getThemeColor('--text-primary'),
            'text-outline-color': getThemeColor('--bg-primary'),
            'text-outline-width': 2,
            'text-valign': 'center',
            'text-halign': 'center',
          },
        },
        {
          selector: 'node.highlighted',
          style: {
            'border-width': 4,
            'border-color': getThemeColor('--error'),
            'width': (ele: CyNodeSingular) => (ele.data('size') || 30) + 15,
            'height': (ele: CyNodeSingular) => (ele.data('size') || 30) + 15,
          },
        },
        {
          selector: 'node.dimmed',
          style: {
            'opacity': 0.15,
          },
        },
        {
          selector: 'edge',
          style: {
            'width': 1,
            'line-color': getThemeColor('--border'),
            'curve-style': 'bezier',
          },
        },
        {
          selector: 'edge.highlighted',
          style: {
            'width': 2,
            'line-color': getThemeColor('--accent'),
            'opacity': 1,
          },
        },
      ],
      layout: {
        name: 'fcose',
        quality: 'proof',
        randomize: true,
        animate: true,
        animationDuration: 800,
        fit: true,
        padding: 80,
        nodeDimensionsIncludeLabels: true,
        ...layoutParams,
      } as CyLayoutOptions,
      minZoom: 0.1,
      maxZoom: 4,
      wheelSensitivity: 0.3,
    })

    cyRef.current = cy
    setNodeCount(filteredData.nodes.length)

    cy.on('tap', 'node', (evt) => {
      const node = evt.target
      const nodeData = nodeMap.get(node.id())
      if (nodeData) {
        setSelectedNode(nodeData)
        
        cy.elements().removeClass('highlighted dimmed')
        node.addClass('highlighted')
        
        const neighborhood = node.neighborhood()
        neighborhood.addClass('highlighted')
        
        cy.elements().difference(neighborhood.union(node)).addClass('dimmed')
      }
    })

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass('highlighted dimmed')
        setSelectedNode(null)
      }
    })

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy()
      }
    }
  }, [filteredData, layoutStrength])

  useEffect(() => {
    if (!cyRef.current || !searchText) return
    
    const cy = cyRef.current
    const matchingNodes = cy.nodes().filter(n => 
      n.data('fullLabel')?.toLowerCase().includes(searchText.toLowerCase()) ||
      n.id().toLowerCase().includes(searchText.toLowerCase())
    )
    
    cy.elements().removeClass('highlighted dimmed')
    
    if (matchingNodes.length > 0) {
      matchingNodes.addClass('highlighted')
      matchingNodes.neighborhood().addClass('highlighted')
      cy.elements().difference(matchingNodes.union(matchingNodes.neighborhood())).addClass('dimmed')
      cy.fit(matchingNodes, 100)
    }
  }, [searchText])

  const handleZoomIn = () => cyRef.current?.zoom(cyRef.current.zoom() * 1.3)
  const handleZoomOut = () => cyRef.current?.zoom(cyRef.current.zoom() / 1.3)
  const handleFit = () => cyRef.current?.fit()
  const handleRelayout = () => {
    if (cyRef.current) {
      const spreadParams = {
        idealEdgeLength: 50,
        nodeRepulsion: 1000000,
        nodeSeparation: 300,
        nestingFactor: 0.01,
        gravity: 0.001,
        gravityRange: 0.1,
        tile: true,
        packComponents: true,
        samplingType: 1,
        samplingSize: 50,
        maxIterations: 3000,
        tilingPaddingVertical: 150,
        tilingPaddingHorizontal: 150,
      }
      const normalParams = {
        idealEdgeLength: 80,
        nodeRepulsion: 500000,
        nodeSeparation: 200,
        nestingFactor: 0.05,
        gravity: 0.005,
        gravityRange: 0.5,
        tile: true,
        packComponents: true,
        samplingType: 1,
        samplingSize: 30,
        maxIterations: 2000,
        tilingPaddingVertical: 100,
        tilingPaddingHorizontal: 100,
      }
      const params = layoutStrength === 'spread' ? spreadParams : normalParams
      
      cyRef.current.layout({
        name: 'fcose',
        quality: 'proof',
        randomize: true,
        animate: true,
        animationDuration: 800,
        fit: true,
        padding: 80,
        nodeDimensionsIncludeLabels: true,
        ...params,
      } as CyLayoutOptions).run()
    }
  }

  return (
    <div className="py-6 animate-fade-in">
      <Title level={2} style={{ color: 'var(--text-primary)', marginBottom: 24 }}>
        <ApartmentOutlined className="mr-2" style={{ color: 'var(--accent)' }} />
        知识图谱
      </Title>

      <Row gutter={16} className="mb-6">
        <Col span={3}>
          <Card className="glass-card-flat">
            <Statistic
              title={<Text style={{ color: 'var(--text-secondary)' }}>节点总数</Text>}
              value={stats?.totalNodes || 0}
              valueStyle={{ color: 'var(--accent)', fontSize: 20 }}
              prefix={<NodeIndexOutlined />}
            />
          </Card>
        </Col>
        <Col span={3}>
          <Card className="glass-card-flat">
            <Statistic
              title={<Text style={{ color: 'var(--text-secondary)' }}>关系总数</Text>}
              value={stats?.totalEdges || 0}
              valueStyle={{ color: 'var(--accent)', fontSize: 20 }}
            />
          </Card>
        </Col>
        <Col span={3}>
          <Card className="glass-card-flat">
            <Statistic
              title={<Text style={{ color: 'var(--text-secondary)' }}>当前显示</Text>}
              value={nodeCount}
              valueStyle={{ color: 'var(--accent)', fontSize: 20 }}
            />
          </Card>
        </Col>
        <Col span={15}>
          <Card className="glass-card-flat">
            <Space wrap size="middle">
              <Select
                value={filterType}
                onChange={setFilterType}
                style={{ width: 120 }}
                options={[
                  { value: 'all', label: '全部类型' },
                  { value: 'paper', label: '论文' },
                  { value: 'entity', label: '实体' },
                  { value: 'concept', label: '概念' },
                  { value: 'synthesis', label: '综述' },
                ]}
              />
              <Select
                value={layoutStrength}
                onChange={setLayoutStrength}
                style={{ width: 140 }}
                options={[
                  { value: 'spread', label: '强分离模式' },
                  { value: 'normal', label: '标准模式' },
                ]}
              />
              <Space>
                <Text style={{ color: 'var(--text-secondary)' }}>只显示有连接的节点</Text>
                <Switch checked={showConnectedOnly} onChange={setShowConnectedOnly} />
              </Space>
              <Input.Search
                placeholder="搜索节点..."
                allowClear
                style={{ width: 180 }}
                onSearch={setSearchText}
                enterButton={<SearchOutlined />}
              />
              <Button.Group>
                <Button icon={<ZoomInOutlined />} onClick={handleZoomIn} title="放大" />
                <Button icon={<ZoomOutOutlined />} onClick={handleZoomOut} title="缩小" />
                <Button icon={<FullscreenOutlined />} onClick={handleFit} title="适应窗口" />
                <Button icon={<ReloadOutlined />} onClick={handleRelayout} title="重新布局" />
              </Button.Group>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card className="glass-card-flat" bodyStyle={{ padding: 0 }}>
        {isLoading ? (
          <div className="flex items-center justify-center h-96">
            <Spin size="large" />
          </div>
        ) : (
          <div className="relative">
            <div className="flex gap-3 p-3 absolute top-2 left-2 z-10">
              {Object.entries(typeNames).filter(([k]) => k !== 'entitie').map(([type, name]) => (
                <Tag key={type} color={getTypeColor(type)}>{name}</Tag>
              ))}
            </div>
            
            <div className="absolute bottom-2 right-2 z-10 text-xs text-right" style={{ color: 'var(--text-muted)' }}>
              <div>点击节点高亮关联 / 滚轮缩放 / 拖拽平移</div>
              <div>节点越大表示连接越多</div>
            </div>
            
            <div
              ref={containerRef}
              style={{ width: '100%', height: '750px', background: 'var(--bg-secondary)', borderRadius: 8 }}
            />
          </div>
        )}
      </Card>

      <Drawer
        title={selectedNode?.label}
        placement="right"
        onClose={() => {
          setSelectedNode(null)
          cyRef.current?.elements().removeClass('highlighted dimmed')
        }}
        open={!!selectedNode}
        width={400}
      >
        {selectedNode && (
          <Descriptions column={1}>
            <Descriptions.Item label="ID">{selectedNode.id}</Descriptions.Item>
            <Descriptions.Item label="类型">
              <Tag color={getTypeColor(selectedNode.type)}>
                {typeNames[selectedNode.type] || selectedNode.type}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="标签">
              {selectedNode.tags.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {selectedNode.tags.map(tag => <Tag key={tag}>{tag}</Tag>)}
                </div>
              ) : (
                <Text type="secondary">无标签</Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="路径">
              <Text copyable style={{ fontSize: 12 }}>{selectedNode.path}</Text>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  )
}
