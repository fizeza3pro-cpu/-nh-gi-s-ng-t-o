import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Inbox } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { AdminUserDetail as AdminUserDetailType } from "@/lib/types";

function fmtDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AdminUserDetail() {
  const { userId } = useParams<{ userId: string }>();
  const [detail, setDetail] = useState<AdminUserDetailType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;
    setDetail(null);
    setError(null);
    api
      .adminUserDetail(userId)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [userId]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 animate-fade-in">
      <Link
        to="/admin/users"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại danh sách user
      </Link>

      {error && (
        <p className="mt-6 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </p>
      )}

      {!detail && !error && (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-5 w-40" />
        </div>
      )}

      {detail && (
        <div className="mb-6 mt-6">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-serif text-2xl font-medium tracking-tight">
              {detail.user.full_name || detail.user.username}
            </h1>
            <Badge
              variant={detail.user.role === "admin" ? "default" : "secondary"}
            >
              {detail.user.role === "admin" ? "Admin" : "User"}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            @{detail.user.username} · Tham gia {fmtDate(detail.user.created_at)}
          </p>
        </div>
      )}

      {detail && (
        <>
          <h2 className="mb-3 text-sm font-semibold text-foreground">
            Lịch sử submit · {detail.responses.length} lượt
          </h2>

          {detail.responses.length === 0 && (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-card py-16 text-center">
              <Inbox className="h-7 w-7 text-muted-foreground" />
              <p className="text-muted-foreground">
                User này chưa submit lượt nào.
              </p>
            </div>
          )}

          {detail.responses.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Thời gian</th>
                    <th className="px-4 py-3 font-medium">Đồ vật</th>
                    <th className="px-4 py-3 text-right font-medium">Flu</th>
                    <th className="px-4 py-3 text-right font-medium">Flex</th>
                    <th className="px-4 py-3 text-right font-medium">Orig</th>
                    <th className="px-4 py-3 text-right font-medium">Elab</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {detail.responses.map((r) => (
                    <tr
                      key={r.response_id}
                      className="transition-colors hover:bg-muted/30"
                    >
                      <td className="whitespace-nowrap px-4 py-3.5 font-mono text-xs text-muted-foreground">
                        {fmtDate(r.created_at)}
                      </td>
                      <td className="px-4 py-3.5 font-medium">{r.item_name}</td>
                      <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                        {r.fluency}
                      </td>
                      <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                        {r.flexibility}
                      </td>
                      <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                        {r.originality}
                      </td>
                      <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                        {r.elaboration}
                      </td>
                      <td className="px-4 py-3.5 text-right">
                        <Link
                          to={`/result/${r.response_id}`}
                          className="inline-flex items-center gap-1 text-sm font-medium text-foreground/80 hover:text-foreground"
                        >
                          Xem <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
