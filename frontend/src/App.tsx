import { Route, Routes } from "react-router-dom";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import Home from "@/pages/Home";
import Test from "@/pages/Test";
import Result from "@/pages/Result";
import Dashboard from "@/pages/Dashboard";
import AdminDashboard from "@/pages/Admindashboard";
import AdminUsers from "@/pages/Adminusers ";
import AdminUserDetail from "@/pages/Adminuserdetail";
import Login from "./components/auth/Login";
import Register from "./components/auth/Register";
import RequireAuth from "./components/auth/RequireAuth";
import RequireAdminLayout from "./components/auth/Requireadminlayout";

export default function App() {
  function PublicLayout({ children }: { children: React.ReactNode }) {
    return (
      <div className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter />
      </div>
    );
  }
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <main className="flex-1">
        <Routes>
          {/* public router */}
          <Route
            path="/"
            element={
              <PublicLayout>
                <Home />
              </PublicLayout>
            }
          />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          {/* protected router — giao diện người dùng, có SiteHeader/Footer chung */}
          <Route element={<RequireAuth />}>
            <Route path="/test/:itemId" element={<Test />} />
            <Route path="/result/:responseId" element={<Result />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Route>

          {/* admin — giao diện TÁCH BIỆT hoàn toàn, sidebar riêng, không dùng SiteHeader/Footer */}
          <Route element={<RequireAdminLayout />}>
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/admin/users" element={<AdminUsers />} />
            <Route path="/admin/users/:userId" element={<AdminUserDetail />} />
          </Route>
        </Routes>
      </main>
    </div>
  );
}
