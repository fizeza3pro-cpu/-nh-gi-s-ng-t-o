import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, Cpu, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { ManagedModel, ModelConfiguration, ModelPoolSnapshot, ThinkingMode } from "@/lib/model-types";

const STATUS: Record<string, string> = {
  NOT_CONFIGURED: "Chưa khai báo", DISABLED: "Đang tắt", NOT_CONFIRMED: "Chưa xác nhận số dư",
  EXHAUSTED: "Hết quota", LOW_BALANCE: "Dưới ngưỡng", READY: "Sẵn sàng", ACTIVE: "Đang dùng", BLOCKED: "Cần kiểm tra model",
};
const EVENT: Record<string, string> = {
  INITIALIZED: "Nhập model từ cấu hình ban đầu", MODEL_SWITCH: "Chuyển model", QUOTA_EXHAUSTED: "BytePlus báo hết quota",
  ACCOUNT_BLOCKED: "Lỗi API key hoặc tài khoản", SETTINGS_UPDATED: "Admin đổi cài đặt", MODEL_UPDATED: "Admin khai báo model", BALANCE_CONFIRMED: "Admin xác nhận số dư",
};
const REQUEST_STATUS: Record<string, string> = {
  IN_FLIGHT: "Đang gọi", SETTLED: "Đã tính token", UNKNOWN: "Chưa rõ usage", RECONCILED: "Đã đối chiếu số dư",
  REJECTED: "Provider từ chối", DUPLICATE: "Phản hồi đã tính", RELEASED: "Đã hoàn giữ chỗ",
};
const number = (value: number | null) => value === null ? "—" : value.toLocaleString("vi-VN");
const date = (value: string | null) => value ? new Date(value).toLocaleString("vi-VN") : "Chưa có";

function SettingsForm({ snapshot, busy, onSave }: { snapshot: ModelPoolSnapshot; busy: boolean;
  onSave: (options: { enabled: boolean; auto_switch: boolean; threshold: number }) => void }) {
  const [enabled, setEnabled] = useState(snapshot.enabled);
  const [automatic, setAutomatic] = useState(snapshot.auto_switch);
  const [threshold, setThreshold] = useState(String(snapshot.threshold));
  return <form onSubmit={event => { event.preventDefault(); onSave({ enabled, auto_switch: automatic, threshold: Number(threshold) }); }}>
    <fieldset disabled={busy || snapshot.provider !== "byteplus"} className="grid gap-5 md:grid-cols-[1fr_1fr_auto] md:items-end">
      <div className="space-y-3 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} className="h-4 w-4 accent-stone-800" /> Bật quản lý model</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={automatic} onChange={event => setAutomatic(event.target.checked)} className="h-4 w-4 accent-stone-800" /> Tự động chuyển model kế tiếp</label>
      </div>
      <label className="text-sm">Token dự phòng tối thiểu
        <Input type="number" min={0} max={1000000} required value={threshold} onChange={event => setThreshold(event.target.value)} className="mt-2 font-mono" />
      </label>
      <Button type="submit">{busy ? "Đang lưu…" : snapshot.blocked_reason ? "Lưu và thử tiếp sau khi sửa lỗi" : "Lưu cài đặt"}</Button>
    </fieldset>
    <p className="mt-4 text-xs leading-5 text-muted-foreground">Khi tắt quản lý, backend dùng cấu hình model cũ và không trừ sổ token này. Hãy đối chiếu số dư trước khi bật lại. Khi chỉ tắt tự chuyển, model hiện tại vẫn được theo dõi token.</p>
  </form>;
}

function ModelEditor({ model, busy, onSave, onBalance, onClose }: { model: ManagedModel; busy: boolean;
  onSave: (value: ModelConfiguration) => void;
  onBalance: (value: { remaining_tokens: number; quota_limit: number; note: string }) => void; onClose: () => void }) {
  const [label, setLabel] = useState(model.label);
  const [modelId, setModelId] = useState(model.model_id ?? "");
  const [quotaKey, setQuotaKey] = useState(model.quota_key ?? "");
  const [enabled, setEnabled] = useState(model.enabled);
  const [context, setContext] = useState(String(model.context_window));
  const [thinking, setThinking] = useState<ThinkingMode>(model.thinking_mode);
  const [balance, setBalance] = useState("");
  const [limit, setLimit] = useState(String(model.quota_limit));
  const [note, setNote] = useState("");
  function save(event: FormEvent) {
    event.preventDefault();
    onSave({ label: label.trim(), model_id: modelId.trim(), quota_key: quotaKey.trim() || modelId.trim(),
      enabled, context_window: Number(context), thinking_mode: thinking });
  }
  return <Card className="mt-5 border-stone-300 shadow-none"><CardContent className="p-5 sm:p-6">
    <div className="flex items-start justify-between gap-4"><div>
      <h2 className="font-serif text-2xl">Khai báo model {model.slot}</h2>
      <p className="mt-2 text-sm text-muted-foreground">Lưu model ở trạng thái tắt → xác nhận số dư → bật model.</p>
    </div><Button variant="ghost" onClick={onClose}>Đóng</Button></div>
    <form onSubmit={save} className="mt-6">
      <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm">Tên hiển thị<Input className="mt-2" required maxLength={160} value={label} onChange={event => setLabel(event.target.value)} /></label>
        <label className="text-sm">Model ID / Endpoint ID<Input className="mt-2 font-mono" required minLength={2} maxLength={255} value={modelId} onChange={event => setModelId(event.target.value)} placeholder="ID dùng khi gọi BytePlus" /></label>
        <label className="text-sm">Nhóm quota / model gốc<Input className="mt-2 font-mono" maxLength={160} value={quotaKey} onChange={event => setQuotaKey(event.target.value)} placeholder="Để trống để dùng Model ID" /></label>
        <label className="text-sm">Cửa sổ ngữ cảnh (token)<Input className="mt-2 font-mono" type="number" min={2048} max={2000000} required value={context} onChange={event => setContext(event.target.value)} /></label>
        <label className="text-sm">Chế độ thinking<select className="mt-2 h-11 w-full rounded-lg border border-input bg-background px-3" value={thinking} onChange={event => setThinking(event.target.value as ThinkingMode)}>
          <option value="auto">Tự nhận diện từ Model ID</option><option value="disabled">Tắt thinking</option><option value="enabled">Bật thinking</option><option value="unsupported">Model không hỗ trợ thinking / reasoning</option>
        </select></label>
        <label className="flex items-center gap-2 self-end py-3 text-sm"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} className="h-4 w-4 accent-stone-800" /> Cho phép sử dụng model này</label>
        <p className="text-xs leading-5 text-muted-foreground sm:col-span-2">Endpoint dùng chung model gốc phải cùng nhóm quota. Tạo thêm endpoint không tạo thêm 500.000 token. Với Endpoint ID, hãy chọn thinking theo model thực tế và kiểm tra kích thước context từ BytePlus.</p>
        <Button type="submit" className="justify-self-start">Lưu khai báo model</Button>
      </fieldset>
    </form>
    <form onSubmit={event => { event.preventDefault(); onBalance({ remaining_tokens: Number(balance), quota_limit: Number(limit), note: note.trim() }); }} className="mt-7 border-t border-border pt-6">
      <h3 className="font-medium">Xác nhận số dư theo console BytePlus</h3>
      <p className="mt-2 text-xs text-muted-foreground">Đối chiếu gần nhất: {date(model.balance_confirmed_at)} · Request gần nhất: {date(model.last_request_at)}</p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">Áp dụng cho mọi model cùng nhóm quota. Chỉ xác nhận sau khi các request đã hoàn tất; usage chưa rõ sẽ được khép lại theo số dư bạn cung cấp.</p>
      <fieldset disabled={busy || !model.model_id} className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="text-sm">Hạn mức tổng<Input type="number" min={1} max={1000000000} required value={limit} onChange={event => setLimit(event.target.value)} className="mt-2 font-mono" /></label>
        <label className="text-sm">Token còn lại hiện tại<Input type="number" min={0} max={Number(limit)} required value={balance} onChange={event => setBalance(event.target.value)} placeholder="Nhập số dư đã kiểm tra" className="mt-2 font-mono" /></label>
        <label className="text-sm sm:col-span-2">Ghi chú đối chiếu<Input className="mt-2" required minLength={3} maxLength={500} value={note} onChange={event => setNote(event.target.value)} placeholder="Ví dụ: Số dư trên console lúc bắt đầu khảo sát" /></label>
        <Button type="submit" variant="outline" className="justify-self-start">Xác nhận số dư</Button>
      </fieldset>
    </form>
  </CardContent></Card>;
}

export default function AdminModels() {
  const [snapshot, setSnapshot] = useState<ModelPoolSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try { const data = await api.adminModels(); if (active) { setSnapshot(current => current && current.revision > data.revision ? current : data); setError(""); } }
      catch (err) { if (active) setError(err instanceof Error ? err.message : "Không thể tải danh sách model."); }
      finally { if (active) { setLoading(false); timer = setTimeout(refresh, 15000); } }
    };
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [reload]);
  async function mutate(action: () => Promise<ModelPoolSnapshot>, success: string) {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try { const data = await action(); setSnapshot(current => current && current.revision > data.revision ? current : data); setMessage(success); }
    catch (err) { setError(err instanceof Error ? err.message : "Không thể lưu cấu hình model."); }
    finally { setBusy(false); }
  }
  const active = snapshot?.models.find(model => model.slot === snapshot.active_slot);
  const next = snapshot?.models.find(model => model.status === "READY" && model.slot !== snapshot.active_slot);
  const editor = snapshot?.models.find(model => model.slot === selected);
  return <div className="mx-auto max-w-7xl space-y-6 px-5 py-8 sm:px-6">
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
      <div><p className="flex items-center gap-2 text-sm text-muted-foreground"><Cpu className="h-4 w-4" /> BytePlus ModelArk</p>
        <h1 className="mt-3 font-serif text-4xl">Model</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">Quản lý 5 model dùng chung API key, theo dõi token và chuyển sang model dự phòng trước khi hết quota.</p></div>
      <Button variant="outline" disabled={busy} onClick={() => setReload(value => value + 1)}><RefreshCw className="h-4 w-4" /> Tải lại</Button>
    </header>
    {error && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{error}</p>}
    {message && <p role="status" className="text-sm text-stone-700">{message}</p>}
    {loading && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Đang tải cấu hình model…</p>}
    {snapshot && <>
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="shadow-none"><CardContent className="p-5"><p className="text-xs text-muted-foreground">Chế độ hoạt động</p><p className="mt-2 font-serif text-xl">{snapshot.enabled ? snapshot.auto_switch ? "Tự động chuyển" : "Giữ model hiện tại" : "Cấu hình cũ từ .env"}</p></CardContent></Card>
        <Card className="shadow-none"><CardContent className="p-5"><p className="text-xs text-muted-foreground">Model đang dùng trong pool</p><p className="mt-2 break-all font-mono text-sm">{snapshot.enabled ? active?.label ?? "Chưa có request" : "Chưa bật quản lý"}</p><p className="mt-2 text-xs text-muted-foreground">Dự phòng tiếp theo: {next?.label ?? "Chưa sẵn sàng"}</p></CardContent></Card>
        <Card className="shadow-none"><CardContent className="p-5"><p className="text-xs text-muted-foreground">API key dùng chung</p><p className="mt-2 font-serif text-xl">{snapshot.api_key_configured ? "Đã cấu hình ở backend" : "Chưa cấu hình"}</p></CardContent></Card>
      </div>
      {snapshot.blocked_reason && <p role="alert" className="border-l-2 border-destructive p-4 text-sm">BytePlus báo lỗi tài khoản hoặc API key. Kiểm tra cấu hình backend rồi bấm lưu cài đặt để tiếp tục.</p>}
      {snapshot.provider !== "byteplus" && <p role="alert" className="text-sm text-destructive">Backend đang dùng {snapshot.provider}. Chức năng này yêu cầu LLM_PROVIDER=byteplus.</p>}
      <Card className="shadow-none"><CardContent className="p-5 sm:p-6"><SettingsForm key={snapshot.revision} snapshot={snapshot} busy={busy}
        onSave={options => void mutate(() => api.adminModelSettings(snapshot.revision, options), "Đã lưu cài đặt model.")} /></CardContent></Card>
      <section>
        <h2 className="font-serif text-2xl">Danh sách ưu tiên</h2>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">Token còn lại là ước tính từ số dư đối chiếu và usage của ứng dụng. Mỗi request giữ chỗ cả input và output dự kiến; model có thể được chuyển sớm hơn ngưỡng. Không cộng hai lần cached/reasoning token đã nằm trong tổng usage.</p>
        <div className="mt-4 overflow-x-auto rounded-lg border border-border bg-card"><table className="w-full min-w-[920px] text-left text-sm">
          <thead className="border-b border-border bg-muted/40 text-xs text-muted-foreground"><tr>{["Ưu tiên / model", "Đã dùng ước tính", "Còn lại ước tính", "Đang giữ chỗ", "Khả dụng", "Trạng thái", ""].map((title, index) => <th key={index} className="px-4 py-3 font-medium">{title}</th>)}</tr></thead>
          <tbody className="divide-y divide-border">{snapshot.models.map(model => <tr key={model.slot}>
            <td className="max-w-64 px-4 py-4"><p className="font-medium">{model.slot}. {model.label}</p><p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{model.model_id ?? "Chưa nhập Model ID"}</p></td>
            <td className="px-4 py-4 font-mono">{number(model.used_tokens)}</td><td className="px-4 py-4 font-mono">{number(model.remaining_tokens)}<p className="mt-1 text-[11px] text-muted-foreground">/ {number(model.quota_limit)}</p></td>
            <td className="px-4 py-4 font-mono">{number(model.reserved_tokens)}{model.unknown_requests > 0 && <p className="mt-1 text-[11px] text-amber-800">{model.unknown_requests} request chưa rõ usage</p>}</td>
            <td className="px-4 py-4 font-mono">{number(model.available_tokens)}</td><td className="px-4 py-4"><span className={`inline-flex rounded border px-2 py-1 text-xs ${model.status === "ACTIVE" ? "border-stone-800 bg-stone-800 text-white" : "border-stone-300 text-stone-600"}`}>{STATUS[model.status] ?? model.status}</span></td>
            <td className="px-4 py-4"><Button variant="outline" size="sm" disabled={busy || snapshot.provider !== "byteplus"} onClick={() => setSelected(model.slot)}>Cấu hình <ArrowRight className="h-3.5 w-3.5" /></Button></td>
          </tr>)}</tbody>
        </table></div>
        {editor && <ModelEditor key={`${editor.slot}-${snapshot.revision}`} model={editor} busy={busy} onClose={() => setSelected(null)}
          onSave={model => void mutate(() => api.adminSaveModel(editor.slot, snapshot.revision, model), "Đã lưu khai báo model.")}
          onBalance={balance => void mutate(() => api.adminModelBalance(editor.slot, snapshot.revision, balance), "Đã xác nhận số dư cho nhóm quota.")} />}
      </section>
      <section className="grid gap-6 lg:grid-cols-2">
        <Card className="shadow-none"><CardContent className="p-5 sm:p-6"><h2 className="font-serif text-2xl">Nhật ký model</h2>
          <ul className="mt-4 divide-y divide-border">{snapshot.events.map(row => <li key={row.id} className="py-3 text-sm"><p className="font-medium">{EVENT[row.event] ?? row.event}</p>
            {row.event === "MODEL_SWITCH" && <p className="mt-1 break-all font-mono text-xs">{String(row.payload.from_model ?? "Bắt đầu")} → {String(row.payload.to_model ?? "")}</p>}
            {typeof row.payload.slot === "number" && <p className="mt-1 break-all text-xs text-muted-foreground">Vị trí {row.payload.slot}{typeof row.payload.model_id === "string" ? ` · ${row.payload.model_id}` : ""}</p>}
            {typeof row.payload.remaining_tokens === "number" && <p className="mt-1 font-mono text-xs">Số dư xác nhận: {number(row.payload.remaining_tokens)}</p>}
            {typeof row.payload.note === "string" && <p className="mt-1 text-xs text-muted-foreground">{row.payload.note}</p>}
            <p className="mt-1 text-[11px] text-muted-foreground">{date(row.created_at)}{row.actor_id ? " · Do admin xử lý" : " · Hệ thống"}</p></li>)}</ul>
          {!snapshot.events.length && <p className="mt-4 text-sm text-muted-foreground">Chưa có nhật ký.</p>}
        </CardContent></Card>
        <Card className="shadow-none"><CardContent className="p-5 sm:p-6"><h2 className="font-serif text-2xl">50 request gần nhất</h2>
          <div className="mt-4 max-h-[36rem] overflow-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b border-border text-muted-foreground"><th className="py-2 pr-3 font-medium">Model / bước</th><th className="py-2 pr-3 font-medium">Token</th><th className="py-2 font-medium">Trạng thái</th></tr></thead>
            <tbody>{snapshot.requests.map(row => <tr key={row.id} className="border-b border-border"><td className="py-3 pr-3"><p className="break-all">{row.model_id}</p><p className="mt-1 font-mono text-[10px] text-muted-foreground">{row.stage}</p><p className="mt-1 text-[10px] text-muted-foreground">{date(row.created_at)}</p></td><td className="py-3 pr-3 font-mono">{number(row.total_tokens)}</td><td className="py-3">{REQUEST_STATUS[row.status] ?? row.status}{row.error_code && <p className="mt-1 break-all text-[10px] text-muted-foreground">{row.error_code}</p>}</td></tr>)}</tbody>
          </table></div>{!snapshot.requests.length && <p className="mt-4 text-sm text-muted-foreground">Chưa có request được quản lý.</p>}
        </CardContent></Card>
      </section>
    </>}
  </div>;
}
