import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/components/auth/auth-context";

/** Bọc quanh route chỉ dành cho admin. Không phải admin -> đá về "/".
 * Dùng lồng bên trong <RequireAuth /> ở App.tsx, nên không cần tự kiểm tra
 * loading/đăng nhập nữa — RequireAuth đã lo phần đó rồi. */
export default function RequireAdmin() {
  const { user } = useAuth();

  if (user?.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}