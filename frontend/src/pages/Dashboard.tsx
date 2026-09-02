import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BarChart3, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { ResponseSummary } from "@/lib/types";

const DIMS = [
  { key: "fluency", label: "Fluency" },
  { key: "flexibility", label: "Flexibility" },
  { key: "originality", label: "Originality" },
  { key: "elaboration", label: "Elaboration" },
] as const;

function fmtDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Dashboard() {
  const [rows, setRows] = useState<ResponseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listResponses()
      .then(setRows)
      .catch((err: Error) => setError(err.message));
  }, []);

  const avg = useMemo(() => {
    if (!rows || rows.length === 0) return null;
    const sum = { fluency: 0, flexibility: 0, originality: 0, elaboration: 0 };
    for (const r of rows) {
      sum.fluency += r.fluency;
      sum.flexibility += r.flexibility;
      sum.originality += r.originality;
      sum.elaboration += r.elaboration;
    }
    const n = rows.length;
    return {
      fluency: sum.fluency / n,
      flexibility: sum.flexibility / n,
      originality: sum.originality / n,
      elaboration: sum.elaboration / n,
    };
  }, [rows]);

  return (
    <div className="animate-fade-in">
      <section className="border-b border-border/80 bg-muted/30">
        <div className="container py-14 md:py-20">
          <p className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            <BarChart3 className="h-3.5 w-3.5" /> Bảng điều khiển
          </p>
          <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight md:text-5xl">
            Lịch sử &amp; điểm trung bình nhóm
          </h1>
          <p className="mt-4 max-w-2xl text-muted-foreground">
            Mọi lượt chấm đã lưu ở máy chủ. So sánh điểm mỗi lượt với trung bình
            toàn nhóm để thấy vị trí tương đối.
          </p>
        </div>
      </section>

      {/* Group averages */}
      {avg && (
        <section className="border-b border-border/80">
          <div className="container py-12">
            <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Trung bình nhóm · {rows?.length} lượt
            </p>
            <div className="mt-6 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-4">
              {DIMS.map((d) => (
                <div key={d.key} className="bg-card p-7">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                    {d.label}
                  </p>
                  <p className="mt-3 font-serif text-4xl tabular-nums leading-none">
                    {avg[d.key].toFixed(1)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* History table */}
      <section>
        <div className="container py-12">
          {error && (
            <p className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
              {error}
            </p>
          )}

          {!rows && !error && (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          )}

          {rows && rows.length === 0 && (
            <div className="flex flex-col items-center gap-5 rounded-xl border border-dashed border-border py-20 text-center">
              <Inbox className="h-8 w-8 text-muted-foreground" />
              <p className="font-serif text-2xl">Chưa có lượt chấm nào.</p>
              <p className="max-w-sm text-muted-foreground">
                Làm một bài test để kết quả xuất hiện ở đây.
              </p>
              <Button asChild>
                <Link to="/#chon-do-vat">
                  Bắt đầu test <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          )}

          {rows && rows.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-border">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-[0.14em] text-muted-foreground">
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
                <tbody className="divide-y divide-border bg-card">
                  {rows.map((r) => (
                    <tr
                      key={r.response_id}
                      className="transition-colors hover:bg-muted/30"
                    >
                      <td className="whitespace-nowrap px-4 py-4 font-mono text-xs text-muted-foreground">
                        {fmtDate(r.created_at)}
                      </td>
                      <td className="px-4 py-4 font-serif text-base">
                        {r.item_name}
                      </td>
                      <td className="px-4 py-4 text-right font-mono tabular-nums">
                        {r.fluency}
                      </td>
                      <td className="px-4 py-4 text-right font-mono tabular-nums">
                        {r.flexibility}
                      </td>
                      <td className="px-4 py-4 text-right font-mono tabular-nums">
                        {r.originality}
                      </td>
                      <td className="px-4 py-4 text-right font-mono tabular-nums">
                        {r.elaboration}
                      </td>
                      <td className="px-4 py-4 text-right">
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
        </div>
      </section>
    </div>
  );
}
