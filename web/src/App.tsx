import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import HomePage from './pages/HomePage'
import QueryPage from './pages/QueryPage'
import KnowledgePage from './pages/KnowledgePage'
import PageDetailPage from './pages/PageDetailPage'
import StatusPage from './pages/StatusPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import UserManagePage from './pages/UserManagePage'
import LogManagePage from './pages/LogManagePage'
import IngestPage from './pages/IngestPage'
import ImportPage from './pages/ImportPage'
import GeneratePage from './pages/GeneratePage'
import SettingsPage from './pages/SettingsPage'
import GraphPage from './pages/GraphPage'
import PDFReaderPage from './pages/PDFReaderPage'
import SurveyPage from './pages/SurveyPage'
import PrivateRoute from './components/PrivateRoute'

const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/register',
    element: <RegisterPage />,
  },
  {
    path: '/',
    element: (
      <PrivateRoute>
        <MainLayout />
      </PrivateRoute>
    ),
    children: [
      { index: true, element: <HomePage /> },
      { path: 'query', element: <QueryPage /> },
      { path: 'query/:queryText', element: <QueryPage /> },
      { path: 'knowledge', element: <KnowledgePage /> },
      { path: 'knowledge/:type', element: <KnowledgePage /> },
      { path: 'knowledge/:type/:id', element: <PageDetailPage /> },
      { path: 'status', element: <StatusPage /> },
      { path: 'graph', element: <GraphPage /> },
      { path: 'pdfs', element: <PDFReaderPage /> },
      { path: 'survey', element: <SurveyPage /> },
      {
        path: 'import',
        element: (
          <PrivateRoute roles={['admin', 'core']}>
            <ImportPage />
          </PrivateRoute>
        ),
      },
      {
        path: 'generate',
        element: (
          <PrivateRoute roles={['admin', 'core']}>
            <GeneratePage />
          </PrivateRoute>
        ),
      },
      {
        path: 'ingest',
        element: (
          <PrivateRoute roles={['admin', 'core']}>
            <IngestPage />
          </PrivateRoute>
        ),
      },
      {
        path: 'admin/users',
        element: (
          <PrivateRoute roles={['admin']}>
            <UserManagePage />
          </PrivateRoute>
        ),
      },
      {
        path: 'admin/logs',
        element: (
          <PrivateRoute roles={['admin', 'maintainer']}>
            <LogManagePage />
          </PrivateRoute>
        ),
      },
      {
        path: 'admin/settings',
        element: (
          <PrivateRoute roles={['admin']}>
            <SettingsPage />
          </PrivateRoute>
        ),
      },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
