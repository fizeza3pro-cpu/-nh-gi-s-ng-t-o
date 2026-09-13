import { Link, NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

export default function SiteHeader() {
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
              Bài kiểm tra công dụng thay thế
            </span>
          </div>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {[
            { to: "/", label: "Trang chủ" },
            { to: "/#phuong-phap", label: "Phương pháp" },
            { to: "/#chon-do-vat", label: "Bắt đầu khảo sát" },
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
        <Link
          to="/#chon-do-vat"
          className="rounded-md border border-foreground px-3 py-2 text-sm font-medium transition-colors hover:bg-foreground hover:text-background"
        >
          Làm khảo sát
        </Link>
      </div>
    </header>
  );
}
