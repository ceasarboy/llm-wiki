import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu, Switch, Typography, Dropdown, Avatar, Button } from 'antd'
import { HomeOutlined, BookOutlined, QuestionCircleOutlined, DashboardOutlined, UserOutlined, TeamOutlined, FileTextOutlined, LogoutOutlined, BulbOutlined, BulbFilled, UploadOutlined, ApartmentOutlined, SettingOutlined, FilePdfOutlined, PlayCircleOutlined, ReadOutlined } from '@ant-design/icons'
import { useAppStore } from '../stores/useAppStore'
import { useAuthStore, canManageUsers, canViewLogs, hasRole } from '../stores/useAuthStore'
import { logout as logoutApi } from '../services/authApi'

const { Header, Content, Footer } = Layout
const { Text } = Typography

export default function MainLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { theme, toggleTheme } = useAppStore()
  const { user, isAuthenticated, logout } = useAuthStore()

  const handleLogout = async () => {
    try {
      await logoutApi()
    } catch {
      // ignore
    }
    logout()
    navigate('/login')
  }

  const menuItems = [
    { key: '/', icon: <HomeOutlined />, label: <Link to="/">首页</Link> },
    { key: '/query', icon: <QuestionCircleOutlined />, label: <Link to="/query">问答</Link> },
    { key: '/knowledge', icon: <BookOutlined />, label: <Link to="/knowledge">知识库</Link> },
    { key: '/graph', icon: <ApartmentOutlined />, label: <Link to="/graph">知识图谱</Link> },
    { key: '/pdfs', icon: <FilePdfOutlined />, label: <Link to="/pdfs">PDF阅读</Link> },
    { key: '/status', icon: <DashboardOutlined />, label: <Link to="/status">状态</Link> },
  ]

  if (hasRole(user, ['admin', 'core'])) {
    menuItems.push({ key: '/import', icon: <UploadOutlined />, label: <Link to="/import">论文导入</Link> })
    menuItems.push({ key: '/generate', icon: <PlayCircleOutlined />, label: <Link to="/generate">论文生成</Link> })
    menuItems.push({ key: '/survey', icon: <ReadOutlined />, label: <Link to="/survey">智能分析</Link> })
  }

  if (canManageUsers(user)) {
    menuItems.push({ key: '/admin/users', icon: <TeamOutlined />, label: <Link to="/admin/users">用户管理</Link> })
  }

  if (canViewLogs(user)) {
    menuItems.push({ key: '/admin/logs', icon: <FileTextOutlined />, label: <Link to="/admin/logs">日志管理</Link> })
  }

  if (canManageUsers(user)) {
    menuItems.push({ key: '/admin/settings', icon: <SettingOutlined />, label: <Link to="/admin/settings">系统设置</Link> })
  }

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
    },
  ]

  return (
    <Layout className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <Header
        className="floating-navbar flex items-center justify-between px-6"
        style={{
          background: 'var(--bg-secondary)',
          height: 64,
        }}
      >
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-2xl">📚</span>
            <Text strong style={{ color: 'var(--text-primary)', fontSize: 18 }}>
              LLM-Wiki
            </Text>
          </Link>
          <Menu
            mode="horizontal"
            selectedKeys={[location.pathname]}
            items={menuItems}
            style={{
              flex: 1,
              border: 'none',
              background: 'transparent',
              minWidth: 0,
            }}
          />
        </div>
        <div className="flex items-center gap-4">
          <Switch
            checkedChildren={<BulbFilled />}
            unCheckedChildren={<BulbOutlined />}
            checked={theme === 'dark'}
            onChange={toggleTheme}
            aria-label="切换主题"
          />
          {isAuthenticated && user ? (
            <Dropdown
              menu={{
                items: userMenuItems,
                onClick: ({ key }) => {
                  if (key === 'logout') {
                    handleLogout()
                  }
                },
              }}
            >
              <div className="flex items-center gap-2 cursor-pointer">
                <Avatar icon={<UserOutlined />} style={{ backgroundColor: 'var(--accent)' }} />
                <Text style={{ color: 'var(--text-primary)' }}>{user.username}</Text>
              </div>
            </Dropdown>
          ) : (
            <div className="flex items-center gap-2">
              <Link to="/login">
                <Button type="default" size="small">登录</Button>
              </Link>
              <Link to="/register">
                <Button type="primary" size="small">注册</Button>
              </Link>
            </div>
          )}
        </div>
      </Header>

      <Content
        className="p-6"
        style={{
          maxWidth: 1400,
          margin: '0 auto',
          width: '100%',
          marginTop: 24,
        }}
      >
        <Outlet />
      </Content>

      <Footer
        className="text-center py-6"
        style={{
          background: 'var(--bg-primary)',
          color: 'var(--text-muted)',
          borderTop: '1px solid var(--border)',
        }}
      >
        <Text style={{ color: 'var(--text-muted)' }}>
          LLM-Wiki v3.0 © 2026 - 知识编译系统
        </Text>
      </Footer>
    </Layout>
  )
}
