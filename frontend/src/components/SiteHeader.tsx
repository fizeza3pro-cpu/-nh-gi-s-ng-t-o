import { Link, NavLink, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";
import { useAuth } from "./auth/auth-context";
import { LogOut } from "lucide-react";

export default function SiteHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  function handleLogout() {
    logout();
    navigate("/");
  }
  return (
    <header className="sticky top-0 z-30 border-b border-border/80 bg-background/80 backdrop-blur">
      <div className="container flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="flex flex-col leading-tight">
            <div className="flex items-center gap-3">
              <div className="grid h-full w-18 place-items-center rounded-md border border-border bg-card font-serif text-base font-semibold tracking-tight">
                DEMO
              </div>
              <span className="font-serif text-base font-medium font-semibold">
                AUT
              </span>
            </div>

            <span className="text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
              Alternative Uses Test
            </span>
          </div>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {[
            { to: "/", label: "Trang chủ" },
            { to: "/#phuong-phap", label: "Phương pháp" },
            { to: "/#chon-do-vat", label: "Bắt đầu test" },
            { to: "/dashboard", label: "Lịch sử" },
          ].map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  // 👇 Chỉ active khi ở đúng route (bỏ qua hash)
                  isActive && "text-foreground",
                )
              }
              end={link.to === "/"}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        {/* <div className="flex items-center justify-center w-30">
          <Button onClick={handleLogout}>Đăng xuất</Button>
        </div> */}
        <div className="ml-2 flex items-center gap-2 border-l border-border/80 pl-3">
          {user ? (
            <>
              <span className="hidden text-sm text-muted-foreground sm:inline">
                {user.full_name || user.username}
                {user.role === "admin" && (
                  <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                    Admin
                  </span>
                )}
              </span>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="mr-1.5 h-4 w-4" />
                Đăng xuất
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/login">Đăng nhập</Link>
              </Button>
              <Button size="sm" asChild>
                <Link to="/register">Đăng ký</Link>
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
