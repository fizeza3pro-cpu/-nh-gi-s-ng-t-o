import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Menu, UserRound, X } from "lucide-react";

import {
  getParticipantIdentity,
  PARTICIPANT_PROFILE_CHANGED,
} from "@/lib/api";
import type { ParticipantIdentity } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function SiteHeader() {
  const location = useLocation();
  const [participant, setParticipant] = useState<ParticipantIdentity | null>(
    getParticipantIdentity,
  );
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const syncParticipant = () => setParticipant(getParticipantIdentity());
    window.addEventListener(PARTICIPANT_PROFILE_CHANGED, syncParticipant);
    window.addEventListener("storage", syncParticipant);
    return () => {
      window.removeEventListener(PARTICIPANT_PROFILE_CHANGED, syncParticipant);
      window.removeEventListener("storage", syncParticipant);
    };
  }, []);

  useEffect(() => setMobileOpen(false), [location.pathname, location.hash]);

  useEffect(() => {
    if (!mobileOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  const navigation = [
    { to: "/", label: "Trang chủ" },
    { to: "/#phuong-phap", label: "Phương pháp" },
    ...(participant ? [{ to: "/history", label: "Lịch sử khảo sát" }] : []),
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-border/80 bg-background/90 backdrop-blur">
      <div className="container flex h-16 items-center justify-between gap-4">
        <Link
          to="/"
          aria-label="AUT — Trang chủ"
          className="group flex min-w-0 items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-foreground/20 bg-card font-serif text-sm font-semibold tracking-tight transition-colors group-hover:bg-muted">
            AUT
          </span>
          <span className="hidden min-w-0 leading-tight sm:block">
            <span className="block truncate font-serif text-sm font-semibold">
              Đánh giá tư duy sáng tạo
            </span>
            <span className="block text-[11px] text-muted-foreground">
              Bài kiểm tra công dụng thay thế
            </span>
          </span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Điều hướng chính">
          {navigation.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isActive && link.to !== "/#phuong-phap" && "text-foreground",
                )
              }
              end={link.to === "/"}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {participant ? (
            <Link
              to="/history"
              className="hidden max-w-48 items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex"
            >
              <UserRound className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="truncate">
                {participant.full_name || "Người tham gia"}
              </span>
            </Link>
          ) : null}
          <button
            type="button"
            aria-label={mobileOpen ? "Đóng menu" : "Mở menu"}
            aria-expanded={mobileOpen}
            aria-controls="public-mobile-menu"
            onClick={() => setMobileOpen((open) => !open)}
            className="grid h-11 w-11 place-items-center rounded-md text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
          >
            {mobileOpen ? (
              <X className="h-5 w-5" aria-hidden="true" />
            ) : (
              <Menu className="h-5 w-5" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {mobileOpen ? (
        <nav
          id="public-mobile-menu"
          aria-label="Điều hướng trên điện thoại"
          className="border-t border-border bg-background px-6 py-4 shadow-lg md:hidden"
        >
          <div className="mx-auto grid max-w-lg gap-1">
            {navigation.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className="rounded-lg px-3 py-3 text-sm font-medium text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {link.label}
              </Link>
            ))}
            {participant ? (
              <p className="mt-2 border-t border-border px-3 pt-4 text-xs text-muted-foreground sm:hidden">
                Hồ sơ: {participant.full_name || "Người tham gia"}
              </p>
            ) : null}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
