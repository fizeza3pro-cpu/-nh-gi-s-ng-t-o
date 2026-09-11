import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { AdminUserSummary } from "@/lib/types";

function fmtDate(iso: string | null): string {
  if (!iso) return "Chưa submit";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AdminUsers() {
  const [users, setUsers] = useState<AdminUserSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .adminListUsers()
      .then(setUsers)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 animate-fade-in">
      <div className="mb-6">
        <h1 className="font-serif text-2xl font-medium tracking-tight">
          Người dùng
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Bấm vào một người dùng để xem toàn bộ lịch sử submit của họ.
        </p>
      </div>

      {error && (
        <p className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </p>
      )}

      {!users && !error && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {users && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Username</th>
                <th className="px-4 py-3 font-medium">Họ tên</th>
                <th className="px-4 py-3 font-medium">Vai trò</th>
                <th className="px-4 py-3 text-right font-medium">
                  Số lượt submit
                </th>
                <th className="px-4 py-3 font-medium">Lần submit gần nhất</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u) => (
                <tr key={u.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3.5 font-mono text-xs">
                    {u.username}
                  </td>
                  <td className="px-4 py-3.5 font-medium">
                    {u.full_name || "—"}
                  </td>
                  <td className="px-4 py-3.5">
                    <Badge
                      variant={u.role === "admin" ? "default" : "secondary"}
                    >
                      {u.role === "admin" ? "Admin" : "User"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                    {u.response_count}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3.5 font-mono text-xs text-muted-foreground">
                    {fmtDate(u.last_submitted_at)}
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <Link
                      to={`/admin/users/${u.id}`}
                      className="inline-flex items-center gap-1 text-sm font-medium text-foreground/80 hover:text-foreground"
                    >
                      Chi tiết <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-muted-foreground"
                  >
                    Chưa có người dùng nào.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
