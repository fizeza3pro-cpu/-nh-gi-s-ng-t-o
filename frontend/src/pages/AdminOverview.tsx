import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpenCheck,
  Database,
  FlaskConical,
  ShieldQuestion,
  Users2,
} from "lucide-react";
import { AreaSparkline } from "@/components/charts/Areasparkline";
import { DonutChart } from "@/components/charts/DonutChart";
import { api } from "@/lib/api";
import type { AdminDashboardStats } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  COLLECTING: "Đang thu thập",
  PENDING_REVIEW: "Chờ xử lý",
  PROVISIONAL: "Trạng thái cũ",
  FINAL: "Điểm chính thức",
  EXCLUDED: "Đã loại",
  CALIBRATING: "Đang hiệu chỉnh",
  ACTIVE: "Đang hoạt động",
  RECALIBRATING: "Đang tái hiệu chỉnh",
  PAUSED: "Tạm dừng",
};

const STATUS_STYLES: Record<string, string> = {
  COLLECTING: "border-stone-300 bg-stone-100 text-stone-700",
  PENDING_REVIEW: "border-amber-200 bg-amber-50 text-amber-800",
  PROVISIONAL: "border-sky-200 bg-sky-50 text-sky-800",
  FINAL: "border-emerald-200 bg-emerald-50 text-emerald-800",
  EXCLUDED: "border-rose-200 bg-rose-50 text-rose-800",
  CALIBRATING: "border-amber-200 bg-amber-50 text-amber-800",
  ACTIVE: "border-emerald-200 bg-emerald-50 text-emerald-800",
  RECALIBRATING: "border-sky-200 bg-sky-50 text-sky-800",
  PAUSED: "border-rose-200 bg-rose-50 text-rose-800",
};

function formatDay(value: string): string {
  return new Date(value).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
  });
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "—";
  return date.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusBadge({ value }: { value: string }) {
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-medium ${STATUS_STYLES[value] ?? STATUS_STYLES.COLLECTING}`}
    >
      {STATUS_LABELS[value] ?? value}
    </span>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  note: string;
}) {
  return (
    <div className="border-l border-stone-300 pl-4 first:border-l-0 first:pl-0 lg:pl-6">
      <div className="flex items-center gap-2 text-stone-500">
        <Icon className="h-4 w-4" />
        <span className="text-xs">{label}</span>
      </div>
      <p className="mt-2 font-mono text-3xl tabular-nums text-stone-900">
        {value.toLocaleString("vi-VN")}
      </p>
      <p className="mt-1 text-xs text-stone-500">{note}</p>
    </div>
  );
}

function Panel({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="border border-stone-200 bg-white p-5 shadow-[0_1px_0_rgba(28,25,23,0.03)] sm:p-6">
      <div className="border-b border-stone-200 pb-4">
        <h2 className="font-serif text-xl text-stone-900">{title}</h2>
        {note && <p className="mt-1 text-sm text-stone-500">{note}</p>}
      </div>
      {children}
    </section>
  );
}

export default function AdminOverview() {
  const [stats, setStats] = useState<AdminDashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.adminDashboard().then(setStats).catch((err: Error) => setError(err.message));
  }, []);

  const trendNote = useMemo(() => {
    if (!stats) return "";
    const current = stats.responses_last_7_days;
    const previous = stats.responses_previous_7_days;
    if (previous === 0) return `${previous} lượt trong 7 ngày trước đó`;
    const change = Math.round(((current - previous) / previous) * 100);
    return `${change >= 0 ? "+" : ""}${change}% so với 7 ngày trước`;
  }, [stats]);

  const scoringData = useMemo(() => {
    if (!stats) return [];
    const status = stats.scoring_status_counts;
    return [
      { label: "Thu thập", value: status.collecting, color: "#78716C" },
      { label: "Chờ xử lý", value: status.pending_review, color: "#D97706" },
      { label: "Tạm thời", value: status.provisional, color: "#0369A1" },
      { label: "Chính thức", value: status.final, color: "#047857" },
      { label: "Đã loại", value: status.excluded, color: "#BE123C" },
    ];
  }, [stats]);

  if (error) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-10">
        <p className="border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 px-6 py-10">
        <div className="h-24 animate-pulse bg-stone-100" />
        <div className="h-72 animate-pulse bg-stone-100" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8 sm:px-6 lg:py-10">
      <header className="mb-8 grid gap-4 border-b border-stone-300 pb-7 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[#8B5E34]">
            Sổ theo dõi nghiên cứu · AUT
          </p>
          <h1 className="mt-3 font-serif text-3xl tracking-tight text-stone-900 sm:text-4xl">
            Tiến độ dữ liệu và sổ mã
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-600">
            Trang tổng quan phản ánh dữ liệu đang được thu thập và mức sẵn sàng để chấm điểm một lần.
          </p>
        </div>
        <Link
          to="/admin/codebooks"
          className="inline-flex items-center gap-2 text-sm font-medium text-[#8B5E34] hover:text-stone-900"
        >
          Mở sổ mã động <ArrowRight className="h-4 w-4" />
        </Link>
      </header>

      <section className="grid grid-cols-2 gap-x-4 gap-y-7 border-b border-stone-300 pb-8 lg:grid-cols-4 lg:gap-x-8">
        <Metric icon={Database} label="Tổng lượt trả lời" value={stats.total_responses} note={`${stats.qualifying_response_count} response đủ điều kiện`} />
        <Metric icon={Users2} label="Người tham gia" value={stats.total_participants} note="Hồ sơ email riêng biệt" />
        <Metric icon={FlaskConical} label="7 ngày gần nhất" value={stats.responses_last_7_days} note={trendNote} />
        <Metric icon={BookOpenCheck} label="Mã được chấp nhận" value={stats.accepted_code_count} note={`${stats.uncertain_code_count} cần theo dõi · ${stats.rejected_code_count} bị loại`} />
      </section>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <Panel title="Nhịp thu thập" note="Số lượt trả lời mới trong 14 ngày gần nhất.">
          <div className="pt-5">
            <AreaSparkline
              values={stats.daily_stats.map((day) => day.count)}
              labels={stats.daily_stats.map((day) => formatDay(day.date))}
              color="#8B5E34"
            />
          </div>
        </Panel>

        <Panel title="Trạng thái chấm điểm" note="Mỗi lượt chỉ thuộc một trạng thái tại thời điểm hiện tại.">
          <div className="flex min-h-48 items-center justify-center pt-5">
            {stats.total_responses > 0 ? (
              <DonutChart data={scoringData} total={stats.total_responses} totalLabel="Lượt" size={156} />
            ) : (
              <div className="text-center text-sm text-stone-500">
                <ShieldQuestion className="mx-auto mb-3 h-7 w-7 text-stone-400" />
                Chưa có lượt trả lời để phân loại.
              </div>
            )}
          </div>
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Tiến độ theo đồ vật" note="Chỉ mở chấm điểm khi đồng thời đủ ngưỡng người tham gia và response.">
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="border-y border-stone-200 bg-stone-50 text-xs text-stone-500">
                <tr>
                  <th className="px-3 py-3 font-medium">Đồ vật</th>
                  <th className="px-3 py-3 font-medium">Trạng thái</th>
                  <th className="px-3 py-3 font-medium">Dữ liệu đủ điều kiện</th>
                  <th className="px-3 py-3 font-medium">Tiến độ</th>
                  <th className="px-3 py-3 font-medium">Mã do AI tạo</th>
                  <th className="px-3 py-3 text-right font-medium">Phiên bản</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-200">
                {stats.by_item.map((item) => {
                  const participantProgress = item.qualifying_participant_count / Math.max(item.scoring_min_participants, 1);
                  const responseProgress = item.qualifying_response_count / Math.max(item.scoring_min_responses, 1);
                  const progress = Math.min(100, Math.round(Math.min(participantProgress, responseProgress) * 100));
                  return (
                    <tr key={item.item_id} className="hover:bg-stone-50/70">
                      <td className="px-3 py-4">
                        <Link to={`/admin/codebooks/${item.item_id}`} className="font-serif text-lg text-stone-900 hover:text-[#8B5E34]">
                          {item.item_name}
                        </Link>
                        <p className="mt-0.5 text-[11px] text-stone-400">{item.response_count} lượt trả lời</p>
                      </td>
                      <td className="px-3 py-4"><StatusBadge value={item.calibration_status} /></td>
                      <td className="px-3 py-4 font-mono tabular-nums text-stone-700">
                        <span>{item.qualifying_response_count} response</span>
                        <span className="mt-1 block text-[11px] text-stone-400">
                          {item.qualifying_participant_count} người
                        </span>
                      </td>
                      <td className="w-48 px-3 py-4">
                        <div className="h-1.5 overflow-hidden bg-stone-200">
                          <div className="h-full bg-[#8B5E34] transition-all" style={{ width: `${progress}%` }} />
                        </div>
                        <p className="mt-1.5 text-[11px] text-stone-500">
                          {item.qualifying_participant_count}/{item.scoring_min_participants} người · {item.qualifying_response_count}/{item.scoring_min_responses} response
                        </p>
                      </td>
                      <td className="px-3 py-4 font-mono text-xs tabular-nums">
                        <span className="text-emerald-700">{item.accepted_code_count} nhận</span>
                        <span className="mx-2 text-stone-300">/</span>
                        <span className="text-amber-700">{item.uncertain_code_count} theo dõi</span>
                        <span className="mx-2 text-stone-300">/</span>
                        <span className="text-rose-700">{item.rejected_code_count} loại</span>
                      </td>
                      <td className="px-3 py-4 text-right font-mono text-xs text-stone-500">
                        {item.active_version ? `v${item.active_version}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Lượt trả lời gần đây" note="Dữ liệu thô được giữ độc lập với trạng thái chấm điểm.">
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[780px] text-left text-sm">
              <thead className="border-y border-stone-200 bg-stone-50 text-xs text-stone-500">
                <tr>
                  <th className="px-3 py-3 font-medium">Thời gian</th>
                  <th className="px-3 py-3 font-medium">Đồ vật</th>
                  <th className="px-3 py-3 font-medium">Trạng thái điểm</th>
                  <th className="px-3 py-3 text-right font-medium">Kết quả</th>
                  <th className="px-3 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-200">
                {stats.recent_responses.map((response) => {
                  const hasScore = response.scoring_status === "FINAL";
                  return (
                    <tr key={response.response_id} className="hover:bg-stone-50/70">
                      <td className="whitespace-nowrap px-3 py-4 font-mono text-xs text-stone-500">{formatDateTime(response.created_at)}</td>
                      <td className="px-3 py-4 font-medium text-stone-800">{response.item_name}</td>
                      <td className="px-3 py-4"><StatusBadge value={response.scoring_status} /></td>
                      <td className="px-3 py-4 text-right font-mono text-xs tabular-nums text-stone-600">
                        {hasScore ? `${response.fluency} · ${response.flexibility} · ${response.originality} · ${response.elaboration}` : "Chưa tính điểm"}
                      </td>
                      <td className="px-3 py-4 text-right">
                        <Link to={`/result/${response.response_id}`} className="inline-flex items-center gap-1 text-xs font-medium text-[#8B5E34] hover:text-stone-900">
                          Xem <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
                {stats.recent_responses.length === 0 && (
                  <tr><td colSpan={5} className="px-3 py-10 text-center text-sm text-stone-500">Chưa có lượt trả lời mới.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
