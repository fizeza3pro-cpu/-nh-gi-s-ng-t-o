import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Archive,
  BookOpen,
  Check,
  CircleX,
  GitBranch,
  GitMerge,
  LockKeyhole,
  ScanSearch,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type {
  AdminCodebookCode,
  AdminCodebookSummary,
  AdminCodePatch,
  AdminCuratorAudit,
  AdminCuratorDecisionIdea,
  AdminExtractionAudit,
} from "@/lib/types";

type Filter = "ALL" | "ACCEPTED" | "UNCERTAIN" | "REJECTED" | "ARCHIVED";
type LedgerView = "CODEBOOK" | "EXTRACTION" | "CURATOR";
type CuratorFilter = "ALL" | "MATCH_EXISTING" | "CREATE_NEW" | "INVALID" | "GUARDED";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "ALL", label: "Tất cả" },
  { value: "ACCEPTED", label: "Được dùng" },
  { value: "UNCERTAIN", label: "AI cần đối chiếu" },
  { value: "REJECTED", label: "Đã loại" },
  { value: "ARCHIVED", label: "Lưu trữ" },
];

const VALIDATION_LABEL = {
  ACCEPTED: "Hợp lệ",
  UNCERTAIN: "Chưa chắc",
  REJECTED: "Đã loại",
} as const;

const MATURITY_LABEL: Record<AdminCodebookCode["maturity_status"], string> = {
  EMERGING: "Đang hình thành",
  STABLE: "Ổn định",
  MERGED: "Đã gộp",
  ARCHIVED: "Đã lưu trữ",
};

const CALIBRATION_LABEL: Record<string, string> = {
  COLLECTING: "Đang thu thập",
  CALIBRATING: "Đang mở chấm điểm",
  ACTIVE: "Đang sử dụng",
  RECALIBRATING: "Đang cập nhật sổ mã",
  PAUSED: "Tạm dừng",
};

const CREATED_BY_LABEL: Record<string, string> = {
  LLM: "AI tạo",
  LLM_REDISCOVERED: "AI tìm lại",
  ADMIN: "Quản trị viên tạo",
  LEGACY: "Dữ liệu cũ",
};

const CURATOR_LABEL: Record<AdminCuratorDecisionIdea["decision"], string> = {
  MATCH_EXISTING: "Khớp mã có sẵn",
  CREATE_NEW: "Tạo mã mới",
  INVALID: "AI loại",
  CURATOR_OBJECT_GUARD: "Hệ thống chặn",
  MISSING_DECISION: "Thiếu quyết định",
};

function ScoringReadiness({ summary }: { summary: AdminCodebookSummary }) {
  const participantProgress = Math.min(
    100,
    (summary.qualifying_participant_count / Math.max(summary.scoring_min_participants, 1)) * 100,
  );
  const responseProgress = Math.min(
    100,
    (summary.qualifying_response_count / Math.max(summary.scoring_min_responses, 1)) * 100,
  );

  return (
    <div className="border-y border-border bg-muted/20 px-5 py-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            Mức sẵn sàng chấm điểm
          </p>
          <p className="mt-2 font-serif text-2xl">Cần đồng thời đủ cả hai ngưỡng</p>
        </div>
        <p className="max-w-56 text-right text-xs leading-5 text-muted-foreground">
          Mỗi response đủ điều kiện sẽ được chấm một lần bằng tần suất tại thời điểm đó.
        </p>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {[
          ["Người tham gia", summary.qualifying_participant_count, summary.scoring_min_participants, participantProgress],
          ["Response đủ điều kiện", summary.qualifying_response_count, summary.scoring_min_responses, responseProgress],
        ].map(([label, current, target, progress]) => (
          <div key={label}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-xs text-muted-foreground">{label}</span>
              <span className="font-mono text-sm">{current} / {target}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border">
              <div className="h-full rounded-full bg-foreground" style={{ width: `${progress}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CodeRow({
  code,
  totalContributingIdeas,
  targets,
  busy,
  onSave,
  onArchive,
  onRestore,
  onMerge,
  onDelete,
}: {
  code: AdminCodebookCode;
  totalContributingIdeas: number;
  targets: AdminCodebookCode[];
  busy: boolean;
  onSave: (patch: AdminCodePatch) => void;
  onArchive: () => void;
  onRestore: () => void;
  onMerge: (target: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(code.name);
  const [description, setDescription] = useState(code.description);
  const [mergeTarget, setMergeTarget] = useState("");

  const inactive = code.maturity_status === "ARCHIVED" || code.maturity_status === "MERGED";

  return (
    <tr className={inactive ? "bg-muted/20 text-muted-foreground" : "bg-card"}>
      <td className="px-4 py-4 align-top">
        {editing ? (
          <div className="space-y-2">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-serif text-base outline-none focus:ring-2 focus:ring-foreground/15"
            />
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={2}
              className="w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-foreground/15"
            />
            <div className="flex gap-2">
              <Button size="sm" disabled={busy} onClick={() => onSave({ name, description })}>
                <Check className="h-3.5 w-3.5" /> Lưu
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Huỷ</Button>
            </div>
          </div>
        ) : (
          <button type="button" className="text-left" onClick={() => setEditing(true)}>
            <span className="font-serif text-base text-foreground">{code.name}</span>
            <span className="mt-1 block max-w-md text-xs leading-relaxed text-muted-foreground">
              {code.description || "Chưa có mô tả phạm vi của mã."}
            </span>
            <span className="mt-2 block text-[11px] text-muted-foreground/80">
              {CREATED_BY_LABEL[code.created_by] ?? "Hệ thống tạo"}
            </span>
          </button>
        )}
      </td>
      <td className="px-4 py-4 align-top">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant={code.validation_status === "ACCEPTED" ? "success" : code.validation_status === "UNCERTAIN" ? "warning" : "secondary"}>
            {VALIDATION_LABEL[code.validation_status]}
          </Badge>
          <Badge variant="outline">{MATURITY_LABEL[code.maturity_status]}</Badge>
          {code.admin_locked && <LockKeyhole className="h-3.5 w-3.5 text-muted-foreground" />}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Độ tin cậy <span className="font-mono text-foreground">{(code.confidence * 100).toFixed(0)}%</span>
        </p>
      </td>
      <td className="px-4 py-4 align-top text-right tabular-nums">
        {code.validation_status === "ACCEPTED" && !inactive ? (
          <div className="ml-auto w-40">
            <div className="flex items-baseline justify-end gap-1.5">
              <span className="font-serif text-2xl text-foreground">{code.contributing_idea_count}</span>
              <span className="text-xs text-muted-foreground">/ {totalContributingIdeas} ý</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-[#8B5E34]"
                style={{ width: `${Math.min(code.frequency * 100, 100)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              <span className="font-mono text-foreground">{(code.frequency * 100).toFixed(1)}%</span>
              {" · "}{code.contributing_participant_count} người
            </p>
          </div>
        ) : (
          <div>
            <p className="font-serif text-xl text-foreground">{code.idea_count} ý liên quan</p>
            <p className="mt-1 text-xs text-muted-foreground">Không dùng để tính điểm</p>
          </div>
        )}
      </td>
      <td className="max-w-xs px-4 py-4 align-top text-xs leading-relaxed text-muted-foreground">
        {code.rejection_reason || code.relevance_reason || "—"}
      </td>
      <td className="px-4 py-4 align-top">
        <div className="flex min-w-44 flex-col gap-2">
          {code.validation_status === "UNCERTAIN" && !inactive ? (
            <Button
              size="sm"
              disabled={busy}
              onClick={() => onSave({ validation_status: "ACCEPTED", admin_locked: true })}
            >
              <Check className="h-3.5 w-3.5" /> Chấp nhận mã
            </Button>
          ) : code.maturity_status === "ARCHIVED" ? (
            <Button size="sm" variant="outline" disabled={busy} onClick={onRestore}>
              <RotateCcw className="h-3.5 w-3.5" /> Khôi phục
            </Button>
          ) : code.maturity_status !== "MERGED" ? (
            <Button size="sm" variant="outline" disabled={busy} onClick={onArchive}>
              <Archive className="h-3.5 w-3.5" /> Lưu trữ
            </Button>
          ) : null}
          {!inactive && targets.length > 0 && (
            <div className="flex gap-1">
              <select
                value={mergeTarget}
                onChange={(event) => setMergeTarget(event.target.value)}
                className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs"
              >
                <option value="">Gộp vào…</option>
                {targets.map((target) => <option key={target.id} value={target.id}>{target.name}</option>)}
              </select>
              <Button size="sm" variant="ghost" disabled={!mergeTarget || busy} onClick={() => onMerge(mergeTarget)}>
                <GitMerge className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
          {code.validation_status === "UNCERTAIN" && !inactive && (
            <Button
              size="sm"
              variant="outline"
              className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
              disabled={busy}
              onClick={() => {
                const confirmed = window.confirm(
                  `Loại mã “${code.name}”? Các ý đang gắn mã này sẽ được đánh dấu không hợp lệ.`,
                );
                if (confirmed) {
                  onSave({ validation_status: "REJECTED", admin_locked: true });
                }
              }}
            >
              <CircleX className="h-3.5 w-3.5" /> Loại mã
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={busy}
            onClick={onDelete}
          >
            <Trash2 className="h-3.5 w-3.5" /> Xoá mã
          </Button>
        </div>
      </td>
    </tr>
  );
}

function PipelineLedgerNav({
  value,
  onChange,
  summary,
  extractionAudit,
  curatorAudit,
}: {
  value: LedgerView;
  onChange: (value: LedgerView) => void;
  summary: AdminCodebookSummary;
  extractionAudit: AdminExtractionAudit | null;
  curatorAudit: AdminCuratorAudit | null;
}) {
  const entries = [
    {
      value: "CODEBOOK" as const,
      label: "Sổ mã đã tạo",
      detail: `${summary.codes.length} mã`,
      icon: BookOpen,
    },
    {
      value: "EXTRACTION" as const,
      label: "Bước tách ý",
      detail: `${extractionAudit?.total_count ?? 0} ý bị loại`,
      icon: CircleX,
    },
    {
      value: "CURATOR" as const,
      label: "Bước đối chiếu mã",
      detail: `${curatorAudit?.total_count ?? 0} quyết định`,
      icon: GitBranch,
    },
  ];

  return (
    <nav aria-label="Các bước kiểm tra sổ mã" className="mt-7 grid overflow-hidden rounded-xl border border-border bg-card md:grid-cols-3">
      {entries.map((entry, index) => {
        const Icon = entry.icon;
        const active = value === entry.value;
        return (
          <button
            key={entry.value}
            type="button"
            onClick={() => onChange(entry.value)}
            aria-current={active ? "page" : undefined}
            className={`group flex items-center gap-3 px-5 py-4 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-foreground/20 ${index > 0 ? "border-t border-border md:border-l md:border-t-0" : ""} ${active ? "bg-[#513827] text-white" : "hover:bg-muted/30"}`}
          >
            <Icon className={`h-4 w-4 shrink-0 ${active ? "text-white" : "text-muted-foreground"}`} />
            <span className="min-w-0">
              <span className="block text-sm font-medium">{entry.label}</span>
              <span className={`mt-0.5 block text-xs ${active ? "text-white/70" : "text-muted-foreground"}`}>
                {entry.detail}
              </span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

function ExtractionLedger({
  audit,
  onOpenResponse,
}: {
  audit: AdminExtractionAudit | null;
  onOpenResponse: (responseId: string) => void;
}) {
  return (
    <section className="mt-7">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div>
          <h2 className="font-serif text-2xl">Ý bị loại trước khi tạo mã</h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            Bước tách ý sàng lọc nội dung không hợp lệ hoặc trùng lặp trước khi đối chiếu mã.
          </p>
        </div>
        <div className="flex overflow-hidden rounded-lg border border-border bg-card text-sm">
          <div className="border-r border-border px-4 py-2.5">
            <span className="font-mono text-rose-800">{audit?.invalid_count ?? 0}</span>
            <span className="ml-2 text-muted-foreground">không hợp lệ</span>
          </div>
          <div className="px-4 py-2.5">
            <span className="font-mono">{audit?.duplicate_count ?? 0}</span>
            <span className="ml-2 text-muted-foreground">trùng lặp</span>
          </div>
        </div>
      </div>

      <div className="mt-5 overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[1050px] text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Ý người tham gia</th>
              <th className="px-4 py-3 font-medium">Kết quả tách ý</th>
              <th className="px-4 py-3 font-medium">Lý do</th>
              <th className="px-4 py-3 font-medium">Nguồn</th>
              <th className="px-4 py-3 font-medium">Thời gian</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {audit?.ideas.map((idea) => (
              <tr key={idea.idea_id} className="bg-card align-top">
                <td className="max-w-md px-4 py-4">
                  <p className="font-serif text-base text-foreground">{idea.original}</p>
                  {idea.normalized && idea.normalized !== idea.original && (
                    <p className="mt-1.5 text-xs text-muted-foreground">Chuẩn hoá: {idea.normalized}</p>
                  )}
                </td>
                <td className="px-4 py-4">
                  <Badge variant={idea.status === "INVALID" ? "destructive" : "secondary"}>
                    {idea.status === "INVALID" ? "Không hợp lệ" : "Trùng lặp"}
                  </Badge>
                </td>
                <td className="max-w-sm px-4 py-4 text-xs leading-relaxed text-muted-foreground">
                  {idea.reason || "AI không cung cấp lý do."}
                </td>
                <td className="px-4 py-4 text-xs text-muted-foreground">
                  <button
                    type="button"
                    onClick={() => onOpenResponse(idea.response_id)}
                    className="inline-flex items-center gap-1 text-[#8B5E34] hover:text-foreground"
                  >
                    Xem lượt trả lời <ArrowRight className="h-3 w-3" />
                  </button>
                </td>
                <td className="whitespace-nowrap px-4 py-4 font-mono text-[11px] text-muted-foreground">
                  {new Date(idea.created_at).toLocaleString("vi-VN")}
                </td>
              </tr>
            ))}
            {(!audit || audit.ideas.length === 0) && (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">
                  Chưa có ý nào bị bước tách ý loại ở đồ vật này.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {audit && audit.displayed_count < audit.total_count && (
        <p className="mt-3 text-right text-xs text-muted-foreground">
          Đang hiển thị {audit.displayed_count}/{audit.total_count} bản ghi mới nhất.
        </p>
      )}
    </section>
  );
}

function CuratorLedger({
  audit,
  onOpenResponse,
}: {
  audit: AdminCuratorAudit | null;
  onOpenResponse: (responseId: string) => void;
}) {
  const [filter, setFilter] = useState<CuratorFilter>("ALL");
  const visibleDecisions = useMemo(() => {
    if (!audit) return [];
    if (filter === "ALL") return audit.decisions;
    if (filter === "GUARDED") {
      return audit.decisions.filter((entry) =>
        ["CURATOR_OBJECT_GUARD", "MISSING_DECISION"].includes(entry.decision),
      );
    }
    return audit.decisions.filter((entry) => entry.decision === filter);
  }, [audit, filter]);
  const filters: { value: CuratorFilter; label: string; count: number }[] = [
    { value: "ALL", label: "Tất cả", count: audit?.total_count ?? 0 },
    { value: "MATCH_EXISTING", label: "Khớp mã có sẵn", count: audit?.match_existing_count ?? 0 },
    { value: "CREATE_NEW", label: "Tạo mã mới", count: audit?.create_new_count ?? 0 },
    { value: "INVALID", label: "AI loại", count: audit?.invalid_count ?? 0 },
    { value: "GUARDED", label: "Hệ thống chặn", count: audit?.guarded_count ?? 0 },
  ];

  const badgeVariant = (decision: AdminCuratorDecisionIdea["decision"]) => {
    if (decision === "MATCH_EXISTING") return "success" as const;
    if (decision === "CREATE_NEW") return "warning" as const;
    if (decision === "INVALID" || decision === "CURATOR_OBJECT_GUARD") return "destructive" as const;
    return "secondary" as const;
  };

  return (
    <section className="mt-7">
      <div className="border-b border-border pb-5">
        <h2 className="font-serif text-2xl">Quyết định đối chiếu mã</h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          Mỗi dòng cho biết AI đã khớp vào mã có sẵn, tạo mã mới hay loại ý tưởng.
        </p>
      </div>
      <div className="mt-5 flex flex-wrap gap-2" role="group" aria-label="Lọc quyết định đối chiếu mã">
        {filters.map((entry) => (
          <button
            key={entry.value}
            type="button"
            onClick={() => setFilter(entry.value)}
            className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${filter === entry.value ? "border-[#513827] bg-[#513827] text-white" : "border-border bg-card text-muted-foreground hover:text-foreground"}`}
          >
            {entry.label} <span className="ml-1 font-mono">{entry.count}</span>
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[1180px] text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Ý đã phân loại</th>
              <th className="px-4 py-3 font-medium">Quyết định</th>
              <th className="px-4 py-3 font-medium">Mã được gán</th>
              <th className="px-4 py-3 font-medium">Độ tin cậy</th>
              <th className="px-4 py-3 font-medium">Lý do</th>
              <th className="px-4 py-3 font-medium">Nguồn</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {visibleDecisions.map((entry) => (
              <tr key={entry.idea_id} className="bg-card align-top">
                <td className="max-w-sm px-4 py-4">
                  <p className="font-serif text-base text-foreground">{entry.original}</p>
                  {entry.normalized && entry.normalized !== entry.original && (
                    <p className="mt-1.5 text-xs text-muted-foreground">Chuẩn hoá: {entry.normalized}</p>
                  )}
                </td>
                <td className="px-4 py-4">
                  <Badge variant={badgeVariant(entry.decision)}>{CURATOR_LABEL[entry.decision]}</Badge>
                </td>
                <td className="max-w-xs px-4 py-4">
                  {entry.code_name ? (
                    <p className="font-medium text-foreground">{entry.code_name}</p>
                  ) : (
                    <span className="text-muted-foreground">Không gắn mã</span>
                  )}
                </td>
                <td className="px-4 py-4 font-mono text-xs tabular-nums">
                  {(entry.confidence * 100).toFixed(0)}%
                </td>
                <td className="max-w-sm px-4 py-4 text-xs leading-relaxed text-muted-foreground">
                  {entry.reason || "AI không cung cấp lý do."}
                </td>
                <td className="px-4 py-4 text-xs text-muted-foreground">
                  <button
                    type="button"
                    onClick={() => onOpenResponse(entry.response_id)}
                    className="inline-flex items-center gap-1 text-[#8B5E34] hover:text-foreground"
                  >
                    Xem lượt trả lời <ArrowRight className="h-3 w-3" />
                  </button>
                  <p className="mt-2">{new Date(entry.created_at).toLocaleString("vi-VN")}</p>
                </td>
              </tr>
            ))}
            {visibleDecisions.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-sm text-muted-foreground">
                  Chưa có quyết định đối chiếu trong nhóm này.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {audit && audit.displayed_count < audit.total_count && (
        <p className="mt-3 text-right text-xs text-muted-foreground">
          Đang hiển thị {audit.displayed_count}/{audit.total_count} quyết định mới nhất.
        </p>
      )}
    </section>
  );
}

function CodebookPicker({
  items,
  onSelect,
}: {
  items: AdminCodebookSummary[];
  onSelect: (itemId: string) => void;
}) {
  return (
    <div className="mx-auto max-w-6xl px-5 py-10 animate-fade-in-up">
      <header className="grid gap-6 border-b border-border pb-8 md:grid-cols-[1fr_18rem] md:items-end">
        <div>
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <BookOpen className="h-4 w-4" /> Danh sách sổ mã
          </p>
          <h1 className="mt-3 max-w-3xl font-serif text-4xl leading-tight">
            Chọn đồ vật cần kiểm tra sổ mã
          </h1>
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Mỗi đồ vật có dữ liệu đóng góp, hệ thống mã và lịch sử thay đổi riêng.
        </p>
      </header>

      <div className="mt-8 overflow-hidden rounded-xl border border-border bg-card">
        <div className="hidden grid-cols-[minmax(0,1fr)_9rem_12rem_7rem_9rem_2rem] gap-5 border-b border-border bg-muted/35 px-5 py-3 text-xs text-muted-foreground md:grid">
          <span>Đồ vật</span>
          <span>Trạng thái</span>
          <span>Điều kiện chấm điểm</span>
          <span className="text-right">Mã đang dùng</span>
          <span className="text-right">Ý bị loại</span>
          <span />
        </div>
        <div className="divide-y divide-border">
          {items.map((item) => {
            const participantProgress = item.qualifying_participant_count / Math.max(item.scoring_min_participants, 1);
            const responseProgress = item.qualifying_response_count / Math.max(item.scoring_min_responses, 1);
            const progress = Math.min(100, Math.min(participantProgress, responseProgress) * 100);
            return (
              <button
                key={item.item_id}
                type="button"
                onClick={() => onSelect(item.item_id)}
                className="grid w-full gap-4 px-5 py-5 text-left transition-colors hover:bg-muted/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-foreground/20 md:grid-cols-[minmax(0,1fr)_9rem_12rem_7rem_9rem_2rem] md:items-center md:gap-5"
              >
                <div>
                  <p className="font-serif text-xl text-foreground">{item.item_name}</p>
                </div>
                <Badge
                  variant={item.calibration_status === "ACTIVE" ? "success" : "secondary"}
                  className="w-fit"
                >
                  {CALIBRATION_LABEL[item.calibration_status] ?? item.calibration_status}
                </Badge>
                <div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="h-full bg-foreground" style={{ width: `${progress}%` }} />
                  </div>
                  <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                    {item.qualifying_participant_count}/{item.scoring_min_participants} người · {item.qualifying_response_count}/{item.scoring_min_responses} response
                  </p>
                </div>
                <p className="font-mono text-lg text-foreground md:text-right">
                  {item.accepted_code_count}
                </p>
                <div className="font-mono text-xs md:text-right">
                  <p className="text-rose-700">{item.extraction_invalid_count} không hợp lệ</p>
                  <p className="mt-1 text-stone-500">{item.extraction_duplicate_count} trùng</p>
                </div>
                <ArrowRight className="hidden h-4 w-4 text-muted-foreground md:block" />
              </button>
            );
          })}
          {items.length === 0 && (
            <p className="px-5 py-16 text-center font-serif text-xl text-muted-foreground">
              Chưa có đồ vật nào trong hệ thống.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AdminCodebooks() {
  const { itemId } = useParams<{ itemId?: string }>();
  const navigate = useNavigate();
  const [items, setItems] = useState<AdminCodebookSummary[]>([]);
  const [summary, setSummary] = useState<AdminCodebookSummary | null>(null);
  const [extractionAudit, setExtractionAudit] = useState<AdminExtractionAudit | null>(null);
  const [curatorAudit, setCuratorAudit] = useState<AdminCuratorAudit | null>(null);
  const [ledgerView, setLedgerView] = useState<LedgerView>("CODEBOOK");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setSummary(null);
    setExtractionAudit(null);
    setCuratorAudit(null);
    setLedgerView("CODEBOOK");
    setError(null);
    Promise.all([
      api.adminListCodebooks(),
      itemId ? api.adminExtractionAudit(itemId) : Promise.resolve(null),
      itemId ? api.adminCuratorAudit(itemId) : Promise.resolve(null),
    ]).then(([data, extraction, curator]) => {
      setItems(data);
      setExtractionAudit(extraction);
      setCuratorAudit(curator);
      if (itemId) {
        const selected = data.find((entry) => entry.item_id === itemId) ?? null;
        setSummary(selected);
        if (!selected) setError("Không tìm thấy sổ mã của đồ vật này.");
      }
    }).catch((err: Error) => setError(err.message)).finally(() => setLoading(false));
  }, [itemId]);

  const visibleCodes = useMemo(() => {
    if (!summary) return [];
    if (filter === "ALL") return summary.codes.filter((code) => code.created_by !== "LEGACY");
    if (filter === "ARCHIVED") return summary.codes.filter((code) => code.maturity_status === "ARCHIVED");
    return summary.codes.filter((code) => code.validation_status === filter);
  }, [filter, summary]);

  const apply = async (
    operation: () => Promise<AdminCodebookSummary>,
    successMessage = "Đã cập nhật sổ mã.",
  ) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const next = await operation();
      setSummary(next);
      setItems((current) => current.map((item) => item.item_id === next.item_id ? next : item));
      const [extraction, curator] = await Promise.all([
        api.adminExtractionAudit(next.item_id),
        api.adminCuratorAudit(next.item_id),
      ]);
      setExtractionAudit(extraction);
      setCuratorAudit(curator);
      setNotice(successMessage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể cập nhật sổ mã.");
    } finally {
      setBusy(false);
    }
  };

  const remapAllResponses = async () => {
    if (!summary) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.adminRemapItem(summary.item_id);
      const [nextSummary, nextExtraction, nextCurator] = await Promise.all([
        api.adminCodebook(summary.item_id),
        api.adminExtractionAudit(summary.item_id),
        api.adminCuratorAudit(summary.item_id),
      ]);
      setSummary(nextSummary);
      setExtractionAudit(nextExtraction);
      setCuratorAudit(nextCurator);
      setItems((current) =>
        current.map((item) =>
          item.item_id === nextSummary.item_id ? nextSummary : item,
        ),
      );
      setNotice(`Đã phân loại lại ${result.processed} lượt trả lời.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể phân loại lại dữ liệu.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="p-8 text-sm text-muted-foreground">Đang tải sổ mã…</div>;
  }

  if (!itemId) {
    return (
      <CodebookPicker
        items={items}
        onSelect={(id) => navigate(`/admin/codebooks/${id}`)}
      />
    );
  }

  if (!summary) {
    return <div className="p-8 text-sm text-destructive">{error || "Không tìm thấy sổ mã."}</div>;
  }

  return (
    <div className="mx-auto max-w-[1500px] px-5 py-8 animate-fade-in-up">
      <header className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5" /> Sổ mã động · AI tự vận hành
          </p>
          <h1 className="mt-2 font-serif text-3xl">Sổ mã của {summary.item_name}</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Mã hợp lệ được dùng tự động. Quản trị viên chỉ xử lý ngoại lệ; mỗi lần gộp hoặc lưu trữ đều tạo phiên bản mới.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => navigate("/admin/codebooks")}>
            <ArrowLeft className="h-4 w-4" /> Chọn đồ vật khác
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => apply(async () => {
            await api.adminReprocessItem(summary.item_id);
            return api.adminCodebook(summary.item_id);
          })}>
            <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> Chấm lại
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => {
              const confirmed = window.confirm(
                `Phân loại lại toàn bộ câu trả lời của “${summary.item_name}”? Hệ thống sẽ chạy lại bước tách ý và đối chiếu mã, thay thế kết quả cũ và có thể làm thay đổi sổ mã.`,
              );
              if (confirmed) void remapAllResponses();
            }}
          >
            <ScanSearch className={`h-4 w-4 ${busy ? "animate-pulse" : ""}`} /> Phân loại lại
          </Button>
          <Button
            variant="outline"
            className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={busy || summary.codes.length === 0}
            onClick={() => {
              const confirmed = window.confirm(
                `Xoá toàn bộ mã của “${summary.item_name}”? Nội dung trả lời gốc vẫn được giữ; mapping, điểm và các phiên bản sẽ được đặt lại để có thể phân loại lại.`,
              );
              if (confirmed) void apply(() => api.adminDeleteAllCodes(summary.item_id));
            }}
          >
            <Trash2 className="h-4 w-4" /> Xoá toàn bộ mã
          </Button>
        </div>
      </header>

      {error && <p className="mt-5 border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</p>}
      {notice && <p className="mt-5 border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">{notice}</p>}

      <div className="mt-7 overflow-hidden rounded-xl border border-border bg-card">
        <div className="grid divide-y divide-border md:grid-cols-[1fr_auto] md:divide-x md:divide-y-0">
          <ScoringReadiness summary={summary} />
          <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-3 md:w-[34rem]">
            {[
              ["Trạng thái", CALIBRATION_LABEL[summary.calibration_status] ?? summary.calibration_status],
              ["Phiên bản", summary.active_version ? `v${summary.active_version}` : "Chưa có"],
              ["Mã đang dùng", summary.accepted_code_count],
              ["Ý cần đối chiếu", summary.pending_idea_count],
              ["Ý bị loại", summary.extraction_invalid_count],
              ["Ý trùng lặp", summary.extraction_duplicate_count],
            ].map(([label, value]) => (
              <div key={label} className="bg-card p-4">
                <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                <p className="mt-2 font-mono text-sm">{value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <PipelineLedgerNav
        value={ledgerView}
        onChange={setLedgerView}
        summary={summary}
        extractionAudit={extractionAudit}
        curatorAudit={curatorAudit}
      />

      {ledgerView === "CODEBOOK" && <>
      <div className="mt-7 flex flex-wrap gap-1 border-b border-border">
        {FILTERS.map((entry) => (
          <button
            key={entry.value}
            type="button"
            onClick={() => setFilter(entry.value)}
            className={`border-b-2 px-3 py-2 text-xs font-medium transition-colors ${filter === entry.value ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[1100px] text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Mã và phạm vi</th>
              <th className="px-4 py-3 font-medium">Phân loại</th>
              <th className="px-4 py-3 text-right font-medium">Tần suất</th>
              <th className="px-4 py-3 font-medium">Lý do của AI</th>
              <th className="px-4 py-3 font-medium">Điều chỉnh</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {visibleCodes.map((code) => (
              <CodeRow
                key={code.id}
                code={code}
                totalContributingIdeas={summary.contributing_idea_count}
                targets={summary.codes.filter((target) => target.id !== code.id && target.validation_status === "ACCEPTED" && !["ARCHIVED", "MERGED"].includes(target.maturity_status))}
                busy={busy}
                onSave={(patch) => apply(
                  () => api.adminUpdateCode(summary.item_id, code.id, patch),
                  patch.validation_status === "ACCEPTED"
                    ? `Đã chấp nhận mã “${code.name}”.`
                    : patch.validation_status === "REJECTED"
                      ? `Đã loại mã “${code.name}”.`
                      : `Đã lưu thay đổi cho mã “${code.name}”.`,
                )}
                onArchive={() => apply(
                  () => api.adminArchiveCode(summary.item_id, code.id),
                  `Đã lưu trữ mã “${code.name}”.`,
                )}
                onRestore={() => apply(
                  () => api.adminRestoreCode(summary.item_id, code.id),
                  `Đã khôi phục mã “${code.name}”.`,
                )}
                onMerge={(target) => apply(
                  () => api.adminMergeCode(summary.item_id, code.id, target),
                  `Đã gộp mã “${code.name}”.`,
                )}
                onDelete={() => {
                  const confirmed = window.confirm(
                    `Xoá mã “${code.name}”? Các câu trả lời đang dùng mã này sẽ chuyển sang chờ phân loại lại.`,
                  );
                  if (confirmed) {
                    void apply(
                      () => api.adminDeleteCode(summary.item_id, code.id),
                      `Đã xoá mã “${code.name}”.`,
                    );
                  }
                }}
              />
            ))}
            {visibleCodes.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-16 text-center font-serif text-xl text-muted-foreground">Chưa có mã ở nhóm này.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      </>}

      {ledgerView === "EXTRACTION" && (
        <ExtractionLedger
          audit={extractionAudit}
          onOpenResponse={(responseId) => navigate(`/result/${responseId}`)}
        />
      )}
      {ledgerView === "CURATOR" && (
        <CuratorLedger
          audit={curatorAudit}
          onOpenResponse={(responseId) => navigate(`/result/${responseId}`)}
        />
      )}
    </div>
  );
}
