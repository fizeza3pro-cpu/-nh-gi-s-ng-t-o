import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/components/auth/auth-context";
import AdminLayout from "@/components/AdminLayout";

/** Guard duy nhất cho khu vực /admin, kèm layout và kiểm tra quyền quản trị. */
export default function AdminRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
        Đang tải...
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/admin/login" state={{ from: location }} replace />;
  }

  if (user.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  return (
    <AdminLayout>
      <Outlet />
    </AdminLayout>
  );
}
