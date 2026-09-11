import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/components/auth/auth-context";
import AdminLayout from "@/components/AdminLayout";

/** Guard riêng cho toàn bộ khu vực /admin — KHÔNG lồng trong RequireAuth,
 * vì admin cần giao diện tách biệt hoàn toàn (sidebar riêng), không dùng
 * chung SiteHeader/SiteFooter của giao diện người dùng công khai. Tự làm
 * lại phần kiểm tra loading/đăng nhập/quyền admin ở đây. */
export default function RequireAdminLayout() {
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
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  if (user.role !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <AdminLayout>
      <Outlet />
    </AdminLayout>
  );
}
