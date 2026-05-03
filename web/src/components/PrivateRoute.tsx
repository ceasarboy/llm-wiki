import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore, hasRole } from '../stores/useAuthStore'

interface PrivateRouteProps {
  children: React.ReactNode
  roles?: string[]
}

export default function PrivateRoute({ children, roles }: PrivateRouteProps) {
  const location = useLocation()
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const user = useAuthStore((state) => state.user)

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (roles && !hasRole(user, roles)) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
