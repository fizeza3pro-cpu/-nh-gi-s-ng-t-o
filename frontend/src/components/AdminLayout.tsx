import { useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Bell,
  Box,
  ChevronDown,
  ClipboardList,
  FileBarChart,
  History,
  LayoutDashboard,
  Layers,
  LogOut,
  Menu,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Users2,
  X,
} from "lucide-react";
import { useAuth } from "@/components/auth/auth-context";

interface NavItem {
  to?: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

const SECTIONS: NavSection[] = [
  {
    label: "Tổng quan",
    items: [
      { to: "/admin", label: "Dashboard", icon: LayoutDashboard },
      { to: "/admin/users", label: "Người dùng", icon: Users2 },
      { label: "Đồ vật", icon: Box, disabled: true },
      { label: "Mục của đồ vật", icon: Layers, disabled: true },
      { label: "Bài test", icon: ClipboardList, disabled: true },
      { label: "Lượt submit", icon: Send, disabled: true },
    ],
  },
  {
    label: "Phân tích",
    items: [
      { label: "Thống kê", icon: FileBarChart, disabled: true },
      { label: "Báo cáo", icon: FileBarChart, disabled: true },
    ],
  },
  {
    label: "Quản trị",
    items: [
      { label: "Quản trị viên", icon: ShieldCheck, disabled: true },
      { label: "Cài đặt hệ thống", icon: Settings, disabled: true },
      { label: "Nhật ký hoạt động", icon: History, disabled: true },
    ],
  },
];

function SidebarContent({ pathname }: { pathname: string }) {
  return (
    <>
      <nav className="flex-1 overflow-y-auto px-4 py-6">
        {SECTIONS.map((section) => (
          <div key={section.label} className="mb-6">
            <p className="mb-2 px-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              {section.label}
            </p>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = item.to && pathname === item.to;

                if (item.disabled || !item.to) {
                  return (
                    <div
                      key={item.label}
                      title="Tính năng đang được thiết kế"
                      className="flex cursor-not-allowed items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted-foreground/50"
                    >
                      <Icon className="h-4 w-4" />
                      {item.label}
                    </div>
                  );
                }

                return (
                  <Link
                    key={item.label}
                    to={item.to}
                    className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${
                      active
                        ? "bg-foreground text-background"
                        : "text-foreground/80 hover:bg-muted"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-4">
        <Link
          to="/"
          className="block rounded-xl border border-border bg-muted/40 p-4 transition-colors hover:bg-muted"
        >
          <p className="font-serif text-sm font-medium">Phương pháp AUT</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Tìm hiểu thêm về phương pháp đánh giá tư duy sáng tạo.
          </p>
          <span className="mt-2 inline-block text-xs font-medium text-foreground/80">
            Xem trang chủ →
          </span>
        </Link>
      </div>
    </>
  );
}

export default function AdminLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      {/* Header trên cùng */}
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur md:px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="rounded-md p-2 hover:bg-muted md:hidden"
            aria-label="Mở menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex h-16 items-center gap-2 border-b border-border px-6">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-foreground text-xs font-bold text-background">
              AUT
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold tracking-tight">
                AUT for Admin
              </p>
              <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                Alternative Uses Test
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled
            title="Sắp có"
            className="hidden cursor-not-allowed rounded-md p-2 text-muted-foreground/50 sm:block"
          >
            <Search className="h-4.5 w-4.5" />
          </button>
          <button
            type="button"
            disabled
            title="Sắp có"
            className="relative hidden cursor-not-allowed rounded-md p-2 text-muted-foreground/50 sm:block"
          >
            <Bell className="h-4.5 w-4.5" />
          </button>

          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-2 rounded-lg border border-border px-2 py-1.5 hover:bg-muted"
            >
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-foreground text-xs font-semibold text-background">
                {(user?.full_name || user?.username || "?")
                  .slice(0, 2)
                  .toUpperCase()}
              </div>
              <span className="hidden text-sm font-medium sm:inline">
                {user?.full_name || user?.username}
              </span>
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            </button>

            {menuOpen && (
              <div className="absolute right-0 top-full mt-2 w-48 rounded-lg border border-border bg-card p-1 shadow-md">
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    logout();
                  }}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-foreground/80 hover:bg-muted"
                >
                  <LogOut className="h-4 w-4" /> Đăng xuất
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar desktop */}
        <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] w-64 flex-col border-r border-border md:flex">
          <SidebarContent pathname={pathname} />
        </aside>

        {/* Sidebar mobile (overlay) với hiệu ứng mượt mà */}
        <div
          className={`fixed inset-0 z-40 md:hidden transition-all duration-300 ${
            mobileOpen ? "visible" : "invisible pointer-events-none"
          }`}
        >
          {/* Lớp nền tối phía sau (Backdrop) */}
          <div
            className={`absolute inset-0 bg-black/30 transition-opacity duration-300 ${
              mobileOpen ? "opacity-100" : "opacity-0"
            }`}
            onClick={() => setMobileOpen(false)}
          />

          {/* Thanh Menu trượt từ trái qua (Sidebar) */}
          <aside
            className={`absolute left-0 top-0 flex h-full w-72 flex-col bg-background shadow-xl transition-transform duration-300 ease-in-out ${
              mobileOpen ? "translate-x-0" : "-translate-x-full"
            }`}
          >
            <div className="flex justify-end p-2">
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="rounded-md p-2 hover:bg-muted"
                aria-label="Đóng menu"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <SidebarContent pathname={pathname} />
          </aside>
        </div>

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
