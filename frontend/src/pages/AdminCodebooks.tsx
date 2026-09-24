import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, FileWarning, Fingerprint, Search, Sparkles } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type {
  AdminCodebookCode,
  AdminCodebookOverview,
  AdminCodebookSummary,
  AdminCuratorAudit,
  AdminExtractionAudit,
  FunctionalSignature,
} from "@/lib/types";

const PAGE_SIZE = 30;
type View = "CODES" | "DECISIONS" | "EXCLUDED";

const decisionLabel: Record<string, string> = {
  MATCH_EXISTING: "Khớp mã đang có",
  CREATE_NEW: "Tạo mã trực tiếp",
  INVALID: "Không hợp lệ",
  UNCERTAIN: "Chưa đủ căn cứ",
  OUT_OF_CODEBOOK: "Ngoài sổ mã",
  POLICY_REJECTED: "Không qua cổng tạo mã",
  CURATOR_OBJECT_GUARD: "Sai đồ vật",
  MISSING_DECISION: "Thiếu quyết định",
};

const gateLabel: Record<string, string> = {
  response_is_valid: "Response hợp lệ",
  no_existing_code_covers: "Không mã nào bao phủ",
  functionally_distinct: "Khác biệt chức năng",
  granularity_consistent: "Cùng mức khái quát",
  paraphrase_stable: "Ổn định khi diễn đạt lại",
  counterexample_passed: "Qua phản ví dụ",
};

function Signature({ value }: { value: FunctionalSignature }) {
  const entries = [
    ["Mục đích", value.goal],
    ["Vai trò", value.object_role],
    ["Cơ chế", value.mechanism],
    ["Biến đổi", value.transformation],
    ["Đối tượng", value.target],
    ["Bối cảnh", value.context],
  ].filter(([, text]) => Boolean(text));
  if (entries.length === 0) return <span className="text-sm text-stone-400">Chưa có chữ ký chức năng</span>;
  return (
    <dl className="grid gap-x-5 gap-y-2 sm:grid-cols-2">
      {entries.map(([label, text]) => (
        <div key={label} className="grid grid-cols-[5rem_1fr] gap-2 text-xs leading-5">
          <dt className="text-stone-400">{label}</dt><dd className="text-stone-700">{text}</dd>
        </div>
      ))}
    </dl>
  );
}

function CodeCard({ code }: { code: AdminCodebookCode }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="border-b border-stone-200 last:border-b-0">
      <button type="button" onClick={() => setOpen((value) => !value)} className="grid w-full gap-4 px-5 py-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#8B5E34]/25 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_7rem_7rem] md:items-center md:px-7">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-serif text-xl text-stone-900">{code.name}</h3>
            <Badge variant="success">Đang hoạt động</Badge>
          </div>
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-stone-500">{code.description}</p>
        </div>
        <div className="text-xs leading-5 text-stone-500">
          <p className="text-stone-400">Khóa chức năng</p>
          <p className="mt-1 break-words font-mono text-[11px] text-stone-700">{code.functional_key || "Chưa chuẩn hóa"}</p>
        </div>
        <div className="md:text-right">
          <p className="text-xs text-stone-400">Ý tưởng</p>
          <p className="mt-1 font-mono text-lg text-stone-900">{code.idea_count}</p>
        </div>
        <div className="md:text-right">
          <p className="text-xs text-stone-400">Tần suất</p>
          <p className="mt-1 font-mono text-lg text-stone-900">{(code.frequency * 100).toFixed(1)}%</p>
        </div>
      </button>
      {open && (
        <div className="mx-4 mb-4 grid gap-6 rounded-lg border border-[#8B5E34]/30 bg-white px-5 py-6 shadow-[0_12px_28px_-24px_rgba(56,39,30,0.65)] md:mx-6 md:grid-cols-2 md:px-6">
          <div>
            <p className="mb-3 flex items-center gap-2 text-sm font-medium text-stone-900"><Fingerprint className="h-4 w-4 text-[#8B5E34]" /> Chữ ký chức năng</p>
            <Signature value={code.functional_signature} />
            <p className="mt-5 text-xs leading-5 text-stone-500">Căn cứ tạo mã: {code.relevance_reason || "Không có mô tả bổ sung."}</p>
          </div>
          <div className="grid gap-4 text-xs leading-5">
            <RuleList title="Được bao gồm" rows={code.inclusion_rules} tone="text-emerald-700" />
            <RuleList title="Không bao gồm" rows={code.exclusion_rules} tone="text-rose-700" />
            <RuleList title="Ví dụ đã dùng" rows={code.positive_examples} tone="text-stone-700" />
          </div>
        </div>
      )}
    </article>
  );
}

function RuleList({ title, rows, tone }: { title: string; rows: string[]; tone: string }) {
  return (
    <div>
      <p className={`font-medium ${tone}`}>{title}</p>
      {rows.length ? <ul className="mt-1 space-y-1 text-stone-600">{rows.map((row, index) => <li key={`${row}-${index}`}>• {row}</li>)}</ul> : <p className="mt-1 text-stone-400">Chưa có dữ liệu.</p>}
    </div>
  );
}

function DecisionEvidence({ reason, value }: { reason: string; value: Record<string, unknown> }) {
  const rawGates = value.policy_gates;
  const gates = rawGates && typeof rawGates === "object" && !Array.isArray(rawGates)
    ? Object.entries(rawGates as Record<string, unknown>)
    : [];
  const challengeReason = typeof value.challenge_reason === "string" ? value.challenge_reason : "";

  return (
    <div>
      <p className="text-xs leading-5 text-stone-600">{reason}</p>
      {gates.length > 0 && (
        <div className="mt-3 flex max-w-sm flex-wrap gap-1.5">
          {gates.map(([gate, passed]) => (
            <span
              key={gate}
              className={`rounded-md border px-2 py-1 text-[10px] leading-4 ${passed ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}
            >
              {passed ? "✓" : "×"} {gateLabel[gate] ?? gate}
            </span>
          ))}
        </div>
      )}
      {challengeReason && <p className="mt-3 border-l-2 border-[#8B5E34] pl-3 text-[11px] leading-5 text-stone-500">Phản biện: {challengeReason}</p>}
    </div>
  );
}

function Picker({ items, onSelect }: { items: AdminCodebookOverview[]; onSelect: (id: string) => void }) {
  return (
    <div className="mx-auto max-w-6xl px-5 py-10">
      <header className="border-b border-stone-300 pb-8">
        <p className="flex items-center gap-2 text-sm text-[#8B5E34]"><BookOpen className="h-4 w-4" /> Sổ mã chức năng</p>
        <h1 className="mt-3 max-w-3xl font-serif text-4xl leading-tight text-stone-900">Theo dõi cách AI hình thành category cho từng đồ vật</h1>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-stone-500">Mã mới được kiểm tra và kích hoạt ngay khi người tham gia gửi bài. Trang này chỉ hiển thị căn cứ, không thay đổi các điểm đã tính.</p>
      </header>
      <div className="mt-8 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-[0_18px_45px_-34px_rgba(56,39,30,0.55)]">
        {items.map((item) => (
          <button key={item.item_id} type="button" onClick={() => onSelect(item.item_id)} className="grid w-full gap-3 border-b border-stone-200 px-5 py-5 text-left last:border-b-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#8B5E34]/25 md:grid-cols-[minmax(0,1fr)_8rem_8rem_2rem] md:items-center">
            <div><p className="font-serif text-xl text-stone-900">{item.item_name}</p><p className="mt-1 text-xs text-stone-400">{item.qualifying_response_count} lượt trả lời · {item.contributing_idea_count} ý đã mã hóa</p></div>
            <div><p className="text-xs text-stone-400">Mã hoạt động</p><p className="mt-1 font-mono text-lg text-stone-800">{item.accepted_code_count}</p></div>
            <div><p className="text-xs text-stone-400">Bị loại/trùng</p><p className="mt-1 font-mono text-lg text-stone-800">{item.extraction_invalid_count + item.extraction_duplicate_count}</p></div>
            <ArrowRight className="hidden h-4 w-4 text-[#8B5E34] md:block" />
          </button>
        ))}
      </div>
    </div>
  );
}

export default function AdminCodebooks() {
  const { itemId } = useParams<{ itemId?: string }>();
  const navigate = useNavigate();
  const [items, setItems] = useState<AdminCodebookOverview[]>([]);
  const [summary, setSummary] = useState<AdminCodebookSummary | null>(null);
  const [audit, setAudit] = useState<AdminCuratorAudit | null>(null);
  const [excluded, setExcluded] = useState<AdminExtractionAudit | null>(null);
  const [view, setView] = useState<View>("CODES");
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true); setError(null);
    const requests = [api.adminListCodebooks()] as const;
    Promise.all([
      ...requests,
      itemId ? api.adminCodebook(itemId, page, PAGE_SIZE, "ACCEPTED") : Promise.resolve(null),
      itemId ? api.adminCuratorAudit(itemId) : Promise.resolve(null),
      itemId ? api.adminExtractionAudit(itemId) : Promise.resolve(null),
    ]).then(([allItems, codebook, curator, extraction]) => {
      setItems(allItems); setSummary(codebook); setAudit(curator); setExcluded(extraction);
    }).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
  }, [itemId, page]);

  const visibleCodes = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("vi");
    if (!normalized) return summary?.codes ?? [];
    return (summary?.codes ?? []).filter((code) => `${code.name} ${code.description} ${code.functional_key}`.toLocaleLowerCase("vi").includes(normalized));
  }, [query, summary]);

  if (loading) return <div className="p-10 text-sm text-stone-500">Đang đọc sổ mã…</div>;
  if (error) return <div className="p-10 text-sm text-red-700">{error}</div>;
  if (!itemId) return <Picker items={items} onSelect={(id) => navigate(`/admin/codebooks/${id}`)} />;
  if (!summary) return <div className="p-10 text-sm text-stone-500">Không tìm thấy sổ mã.</div>;

  const tabs: Array<[View, string, number]> = [
    ["CODES", "Mã đang hoạt động", summary.accepted_code_count],
    ["DECISIONS", "Nhật ký phân xử", audit?.total_count ?? 0],
    ["EXCLUDED", "Ý bị loại", excluded?.total_count ?? 0],
  ];

  return (
    <div className="min-h-[calc(100vh-4rem)] animate-fade-in bg-[#F7F4EF]">
      <header className="border-b border-stone-200 bg-white px-5 py-7 md:px-8">
        <Button variant="ghost" size="sm" onClick={() => navigate("/admin/codebooks")} className="-ml-3 text-stone-500 hover:bg-[#8B5E34]/[0.07] hover:text-stone-900"><ArrowLeft className="h-4 w-4" /> Các đồ vật</Button>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-5">
          <div><p className="flex items-center gap-2 text-sm text-[#8B5E34]"><Sparkles className="h-4 w-4" /> AI tạo mã và tính điểm trực tiếp</p><h1 className="mt-2 font-serif text-4xl text-stone-900">{summary.item_name}</h1></div>
          <div className="flex gap-8"><Stat label="Mã hoạt động" value={summary.accepted_code_count} /><Stat label="Ý đã mã hóa" value={summary.contributing_idea_count} /><Stat label="Lượt gửi" value={summary.qualifying_response_count} /></div>
        </div>
      </header>

      <div className="px-5 py-7 md:px-8">
        <div className="flex flex-wrap gap-1 border-b border-stone-300">
          {tabs.map(([value, label, count]) => <button key={value} type="button" onClick={() => setView(value)} className={`rounded-t-md border-b-2 px-4 py-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8B5E34]/25 ${view === value ? "border-[#8B5E34] bg-[#8B5E34]/[0.06] text-stone-900" : "border-transparent text-stone-500 hover:text-stone-800"}`}>{label} <span className="ml-2 font-mono text-xs">{count}</span></button>)}
        </div>

        {view === "CODES" && <section className="mt-6 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-[0_18px_45px_-34px_rgba(56,39,30,0.55)]">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-stone-200 bg-[#FFFEFC] px-5 py-4 md:px-7">
            <div><h2 className="font-serif text-2xl text-stone-900">Category chức năng</h2><p className="mt-1 text-xs text-stone-500">Mở từng mã để xem goal, role, mechanism và ranh giới áp dụng.</p></div>
            <label className="flex w-full max-w-sm items-center gap-2 rounded-lg border border-stone-200 bg-[#FBF8F4] px-3 py-2 shadow-inner transition-colors focus-within:border-[#8B5E34]/45 focus-within:ring-2 focus-within:ring-[#8B5E34]/10"><Search className="h-4 w-4 text-stone-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm tên, định nghĩa hoặc functional key" className="w-full bg-transparent text-sm text-stone-800 outline-none placeholder:text-stone-400" /></label>
          </div>
          {visibleCodes.map((code) => <CodeCard key={code.id} code={code} />)}
          {visibleCodes.length === 0 && <p className="px-6 py-14 text-center text-sm text-stone-500">Không có mã phù hợp.</p>}
          {summary.code_page_count > 1 && <div className="flex items-center justify-end gap-3 border-t border-stone-200 bg-[#FFFEFC] px-5 py-4"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Trang trước</Button><span className="font-mono text-xs text-stone-500">{page}/{summary.code_page_count}</span><Button size="sm" variant="outline" disabled={page >= summary.code_page_count} onClick={() => setPage((value) => value + 1)}>Trang sau</Button></div>}
        </section>}

        {view === "DECISIONS" && (
          <section className="mt-6 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-[0_18px_45px_-34px_rgba(56,39,30,0.55)]">
            <div className="border-b border-stone-200 bg-[#FFFEFC] px-5 py-5 md:px-7">
              <h2 className="font-serif text-2xl text-stone-900">Nhật ký phân xử</h2>
              <p className="mt-1 text-sm text-stone-500">Mỗi quyết định giữ lại response gốc, chữ ký chức năng và bằng chứng tại thời điểm chấm.</p>
            </div>
            <div className="divide-y divide-stone-200">
              {audit?.decisions.map((decision) => (
                <article key={decision.idea_id} className="px-5 py-6 md:px-7">
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1.6fr)_auto_minmax(0,1fr)] md:items-start">
                    <div>
                      <p className="text-base font-medium leading-6 text-stone-900">{decision.original}</p>
                      <p className="mt-1 text-xs leading-5 text-stone-400">{decision.normalized}</p>
                    </div>
                    <Badge variant={decision.decision === "CREATE_NEW" ? "success" : decision.decision === "MATCH_EXISTING" ? "outline" : decision.decision === "INVALID" ? "destructive" : "warning"}>{decisionLabel[decision.decision] ?? decision.decision}</Badge>
                    <div className="md:text-right">
                      <p className="text-[10px] uppercase tracking-[0.14em] text-stone-400">Category</p>
                      <p className="mt-1 font-mono text-xs text-stone-700">{decision.code_name ?? "Chưa gán mã"}</p>
                    </div>
                  </div>
                  <div className="mt-5 grid gap-4 lg:grid-cols-2">
                    <div className="rounded-lg border border-stone-200 bg-[#FBF8F4] p-4">
                      <p className="mb-3 text-[10px] uppercase tracking-[0.14em] text-stone-400">Functional signature</p>
                      <Signature value={decision.functional_signature} />
                    </div>
                    <div className="rounded-lg border border-stone-200 bg-white p-4">
                      <p className="mb-3 text-[10px] uppercase tracking-[0.14em] text-stone-400">Căn cứ quyết định</p>
                      <DecisionEvidence reason={decision.reason} value={decision.mapping_evidence} />
                    </div>
                  </div>
                </article>
              ))}
              {!audit?.decisions.length && <p className="px-5 py-14 text-center text-sm text-stone-500">Chưa có quyết định phân xử.</p>}
            </div>
          </section>
        )}

        {view === "EXCLUDED" && <section className="mt-6 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-[0_18px_45px_-34px_rgba(56,39,30,0.55)]"><div className="border-b border-stone-200 bg-[#FFFEFC] px-6 py-5"><p className="flex items-center gap-2 font-serif text-2xl text-stone-900"><FileWarning className="h-5 w-5 text-rose-600" /> Response không được mã hóa</p><p className="mt-1 text-sm text-stone-500">Giữ nguyên dữ liệu gốc cùng lý do loại hoặc trùng.</p></div><div className="divide-y divide-stone-200">{excluded?.ideas.map((idea) => <div key={idea.idea_id} className="grid gap-3 px-6 py-4 md:grid-cols-[8rem_minmax(0,1fr)_minmax(0,1fr)]"><Badge variant={idea.status === "DUPLICATE" ? "secondary" : "destructive"}>{idea.status === "DUPLICATE" ? "Trùng ý" : "Không hợp lệ"}</Badge><div><p className="text-sm text-stone-900">{idea.original}</p><p className="mt-1 text-xs text-stone-400">{idea.normalized}</p></div><p className="text-xs leading-5 text-stone-500">{idea.reason}</p></div>)}</div></section>}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div className="text-right"><p className="text-xs text-stone-400">{label}</p><p className="mt-1 font-mono text-xl text-stone-900">{value}</p></div>;
}
