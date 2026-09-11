import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Box, Send, Sparkles, Users2 } from "lucide-react";
import { api } from "@/lib/api";
import type { AdminDashboardStats } from "@/lib/types";
import { AreaSparkline } from "@/components/charts/Areasparkline";
import { DonutChart } from "@/components/charts/DonutChart";

const WARM_PALETTE = ["#3D2B1F", "#8B5E34", "#C89B6E", "#D9C2A0", "#A8A29E"];
const LINE_COLOR = "#8B5E34";

const DIM_LABELS = [
  { key: "fluency", label: "Fluency" },
  { key: "flexibility", label: "Flexibility" },
  { key: "originality", label: "Originality" },
  { key: "elaboration", label: "Elaboration" },
] as const;

function fmtDayLabel(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

function fmtDateTime(iso: string): string {
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

function StatCard({
  icon: Icon,
  label,
  value,
  deltaLabel,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  deltaLabel?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="text-[11px] font-medium uppercase tracking-[0.12em]">
          {label}
        </span>
      </div>
      <p className="mt-3 text-2xl font-bold tabular-nums tracking-tight">
        {value}
      </p>
      {deltaLabel && (
        <p className="mt-1 text-xs font-medium text-emerald-600">
          {deltaLabel}
        </p>
      )}
    </div>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      {children}
    </div>
  );
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<AdminDashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .adminDashboard()
      .then(setStats)
      .catch((err: Error) => setError(err.message));
  }, []);

  const pctChange = useMemo(() => {
    if (!stats) return 0;
    const { responses_last_7_days: cur, responses_previous_7_days: prev } =
      stats;
    if (prev === 0) return cur > 0 ? 100 : 0;
    return Math.round(((cur - prev) / prev) * 100);
  }, [stats]);

  const dayLabels = useMemo(
    () => (stats ? stats.daily_stats.map((d) => fmtDayLabel(d.date)) : []),
    [stats],
  );

  const donutData = useMemo(() => {
    if (!stats) return [];
    return stats.by_item.map((item, i) => ({
      label: item.item_name,
      value: item.response_count,
      color: WARM_PALETTE[i % WARM_PALETTE.length],
    }));
  }, [stats]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 animate-fade-in-up">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-medium tracking-tight">
            Dashboard
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Tổng quan hệ thống chấm điểm tư duy sáng tạo theo phương pháp AUT.
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </p>
      )}

      {!stats && !error && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-28 animate-pulse rounded-xl border border-border bg-card"
            />
          ))}
        </div>
      )}

      {stats && (
        <div className="space-y-6">
          {/* Stat cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={Users2}
              label="Người dùng"
              value={stats.total_users}
            />
            <StatCard icon={Box} label="Đồ vật" value={stats.by_item.length} />
            <StatCard
              icon={Send}
              label="Lượt submit"
              value={stats.total_responses.toLocaleString("vi-VN")}
              deltaLabel={
                pctChange >= 0
                  ? `+${pctChange}% so với tuần trước`
                  : `${pctChange}% so với tuần trước`
              }
            />
            <StatCard
              icon={Sparkles}
              label="7 ngày qua"
              value={stats.responses_last_7_days}
              deltaLabel={`${stats.responses_previous_7_days} lượt tuần trước`}
            />
          </div>

          {/* Line + Donut */}
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <Panel title="Lượt submit theo thời gian">
              <div className="mt-4">
                <AreaSparkline
                  values={stats.daily_stats.map((d) => d.count)}
                  labels={dayLabels}
                  color={LINE_COLOR}
                />
              </div>
            </Panel>
            <Panel title="Phân bố lượt submit theo đồ vật">
              <div className="mt-5 flex justify-center">
                {donutData.length > 0 ? (
                  <DonutChart
                    data={donutData}
                    total={stats.total_responses}
                    totalLabel="Tổng"
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Chưa có dữ liệu.
                  </p>
                )}
              </div>
            </Panel>
          </div>

          {/* Top users */}
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Top người dùng (điểm tổng cao nhất)">
              <div className="mt-4 overflow-hidden rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">#</th>
                      <th className="px-3 py-2 font-medium">Người dùng</th>
                      <th className="px-3 py-2 text-right font-medium">
                        Điểm tổng
                      </th>
                      <th className="px-3 py-2 text-right font-medium">
                        Submit
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {stats.top_users_by_total.map((u, i) => (
                      <tr key={u.user_id}>
                        <td className="px-3 py-2.5 text-muted-foreground">
                          {i + 1}
                        </td>
                        <td className="px-3 py-2.5 font-medium">
                          {u.full_name || u.username}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                          {u.total_score}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono tabular-nums text-muted-foreground">
                          {u.submit_count}
                        </td>
                      </tr>
                    ))}
                    {stats.top_users_by_total.length === 0 && (
                      <tr>
                        <td
                          colSpan={4}
                          className="px-3 py-6 text-center text-muted-foreground"
                        >
                          Chưa có dữ liệu.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Top người dùng theo từng chỉ số">
              <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                {DIM_LABELS.map((dim) => (
                  <div key={dim.key}>
                    <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground">
                      {dim.label}
                    </p>
                    <ul className="space-y-2">
                      {stats.top_users_by_dimension[dim.key].map((u) => (
                        <li
                          key={u.user_id}
                          className="flex items-center justify-between text-sm"
                        >
                          <span className="truncate pr-2">
                            {u.full_name || u.username}
                          </span>
                          <span className="font-mono tabular-nums text-muted-foreground">
                            {u.avg_value}
                          </span>
                        </li>
                      ))}
                      {stats.top_users_by_dimension[dim.key].length === 0 && (
                        <li className="text-xs text-muted-foreground">—</li>
                      )}
                    </ul>
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          {/* Recent */}
          <Panel title="Lượt submit gần đây">
            <div className="mt-4 overflow-hidden rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Thời gian</th>
                    <th className="px-3 py-2 font-medium">Người dùng</th>
                    <th className="px-3 py-2 font-medium">Đồ vật</th>
                    <th className="px-3 py-2 text-right font-medium">Flu</th>
                    <th className="px-3 py-2 text-right font-medium">Flex</th>
                    <th className="px-3 py-2 text-right font-medium">Orig</th>
                    <th className="px-3 py-2 text-right font-medium">Elab</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {stats.recent_responses.map((r) => (
                    <tr key={r.response_id} className="hover:bg-muted/30">
                      <td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs text-muted-foreground">
                        {fmtDateTime(r.created_at)}
                      </td>
                      <td className="px-3 py-2.5 font-medium">{r.username}</td>
                      <td className="px-3 py-2.5">{r.item_name}</td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                        {r.fluency}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                        {r.flexibility}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                        {r.originality}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                        {r.elaboration}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <Link
                          to={`/result/${r.response_id}`}
                          className="inline-flex items-center gap-1 text-sm font-medium text-foreground/80 hover:text-foreground"
                        >
                          Xem <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                  {stats.recent_responses.length === 0 && (
                    <tr>
                      <td
                        colSpan={8}
                        className="px-3 py-8 text-center text-muted-foreground"
                      >
                        Chưa có lượt submit nào.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
