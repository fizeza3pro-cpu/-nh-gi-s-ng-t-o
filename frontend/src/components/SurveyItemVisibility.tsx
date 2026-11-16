import { useEffect, useState } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { getSurveyItems } from "@/lib/survey-items";
import type { Item } from "@/lib/types";

export default function SurveyItemVisibility() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError(null);
    api.listItems().then((data) => {
      if (active) setItems(getSurveyItems(data, true));
    }).catch((err) => {
      if (active) setError(err instanceof Error ? err.message : "Không thể tải danh sách đồ vật.");
    });
    return () => { active = false; };
  }, [loadAttempt]);

  async function toggleVisibility(item: Item) {
    if (savingId) return;
    const visible = item.survey_visible === false;
    setSavingId(item.id);
    setError(null);
    setMessage("");
    try {
      const updated = await api.adminSetSurveyVisibility(item.id, visible);
      setItems((current) => current?.map((row) => row.id === item.id
        ? { ...row, survey_visible: updated.survey_visible }
        : row) ?? null);
      setMessage(`Đã ${visible ? "hiện" : "ẩn"} ${item.name} trên trang chọn khảo sát.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể lưu trạng thái đồ vật.");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <section aria-labelledby="survey-visibility-title" className="mt-6 border border-stone-200 bg-white p-5 sm:p-6">
      <div className="border-b border-stone-200 pb-4">
        <h2 id="survey-visibility-title" className="font-serif text-xl text-stone-900">Đồ vật khảo sát</h2>
        <p className="mt-1 text-sm text-stone-500">Chọn đồ vật hiển thị trên trang chọn bài của người tham gia.</p>
      </div>
      {error && <p role="alert" className="mt-4 text-sm text-destructive">{error}</p>}
      {!items && !error && <p role="status" className="mt-4 text-sm text-muted-foreground">Đang tải đồ vật…</p>}
      {!items && error && <Button variant="outline" className="mt-3" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>Thử lại</Button>}
      {items && items.length === 0 && <p className="mt-4 text-sm text-muted-foreground">Chưa có đồ vật khảo sát.</p>}
      {items && items.length > 0 && (
        <ul className="mt-4 grid gap-x-6 sm:grid-cols-2">
          {items.map((item) => {
            const visible = item.survey_visible !== false;
            return (
              <li key={item.id} className="flex items-center justify-between gap-4 border-b border-stone-100 py-3">
                <div>
                  <p className="text-sm font-medium text-stone-900">{item.name}</p>
                  <p className="mt-1 text-xs text-stone-500">{visible ? "Đang hiện" : "Đang ẩn"}</p>
                </div>
                <Button variant="outline" size="sm" role="switch" aria-checked={visible}
                  aria-label={`Hiển thị ${item.name} trên trang chọn khảo sát`}
                  disabled={savingId !== null} onClick={() => void toggleVisibility(item)}>
                  {savingId === item.id ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    : visible ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                  {savingId === item.id ? "Đang lưu…" : visible ? "Ẩn" : "Hiện"}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <p role="status" className="mt-3 text-sm text-stone-600">{message}</p>
    </section>
  );
}
