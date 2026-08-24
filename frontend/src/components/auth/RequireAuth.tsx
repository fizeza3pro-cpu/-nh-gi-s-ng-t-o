import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/components/auth/auth-context";

export default function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="container py-16 text-center text-muted-foreground">
        Đang tải...
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
