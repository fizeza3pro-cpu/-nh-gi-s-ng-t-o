import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Loader2, Send, Sparkles, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import ParticipantProfileForm from "@/components/participant/ParticipantProfileForm";
import {
  api,
  cacheResponse,
  clearParticipantProfile,
  getParticipantIdentity,
  hasParticipantProfile,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Item, ParticipantIdentity } from "@/lib/types";

export default function Test() {
  const { itemId } = useParams<{ itemId: string }>();
  const navigate = useNavigate();

  const [item, setItem] = useState<Item | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [profileReady, setProfileReady] = useState(hasParticipantProfile);
  const [participant, setParticipant] = useState<ParticipantIdentity | null>(
    getParticipantIdentity,
  );

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load item data
  useEffect(() => {
    if (!itemId) return;
    api
      .getItem(itemId)
      .then(setItem)
      .catch((err: Error) => setLoadError(err.message));
  }, [itemId]);

  // UX: Auto-focus vào textarea khi load xong để người dùng có thể bắt đầu ngay
  useEffect(() => {
    if (item && profileReady && textareaRef.current) {
      // Delay nhẹ để đảm bảo animation render xong
      const timer = setTimeout(() => {
        textareaRef.current?.focus();
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [item, profileReady]);

  const handleSubmit = async () => {
    if (!itemId || !text.trim() || submitting) return;

    setSubmitError(null);
    setSubmitting(true);

    try {
      const resp = await api.score(itemId, text);
      cacheResponse(resp);
      // Truyền response trực tiếp cho route đích để Result render ngay trong cùng lượt
      // điều hướng; sessionStorage chỉ còn là fallback cho F5/mở lại tab.
      navigate(`/result/${resp.response_id}`, { state: { response: resp } });
    } catch (err) {
      const message = (err as Error).message;
      if (message.includes("hồ sơ người tham gia")) {
        clearParticipantProfile();
        setParticipant(null);
        setProfileReady(false);
      }
      setSubmitError(message);
      setSubmitting(false);
    }
  };

  const charCount = text.length;
  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
  const isReadyToSubmit = text.trim().length > 0 && !submitting;

  // Loading / Error States
  if (loadError) {
    return (
      <div className="container flex min-h-[60vh] max-w-xl flex-col items-center justify-center py-24 text-center">
        <p className="font-serif text-2xl text-destructive">
          Không tải được dữ liệu.
        </p>
        <p className="mt-2 text-muted-foreground">{loadError}</p>
        <Button asChild variant="outline" className="mt-6">
          <Link to="/">Quay lại trang chủ</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="animate-in fade-in duration-500">
      {/* --- STICKY HEADER: Tối giản, tập trung vào ngữ cảnh --- */}
      <div className="sticky top-0 z-20 border-b border-border/80 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        {/* Modern Divider: Thay thế cho thanh progress bar chạy theo thời gian */}
        <div className="h-[2px] w-full bg-gradient-to-r from-transparent via-primary/20 to-transparent" />
      </div>

      {/* --- MAIN CONTENT: Bố cục 2 cột hài hòa --- */}
      {!profileReady ? (
        <div className="container py-10 md:py-16">
          <ParticipantProfileForm
            onComplete={(identity) => {
              setParticipant(identity);
              setProfileReady(true);
            }}
          />
        </div>
      ) : (
      <section className="container grid gap-10 py-10 md:grid-cols-[1fr_1.4fr] md:py-16">
        {/* Cột trái: Thông tin đồ vật & Hướng dẫn (Sticky khi cuộn) */}
        <aside className="md:sticky md:top-28 md:self-start">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Đối tượng
            </p>
          </div>

          {item ? (
            <h1 className="mt-3 font-serif text-5xl font-medium tracking-tight text-foreground md:text-6xl">
              {item.name}
            </h1>
          ) : (
            <Skeleton className="mt-3 h-14 w-40" />
          )}

          {item ? (
            <p className="mt-5 max-w-sm text-pretty text-lg leading-relaxed text-muted-foreground">
              {item.description}
            </p>
          ) : (
            <Skeleton className="mt-5 h-16 w-full max-w-sm" />
          )}

          {participant && (
            <div className="mt-6 flex max-w-sm items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <UserRound className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {participant.full_name || "Người tham gia"}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {participant.email_masked || "Email đã liên kết"}
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="shrink-0 text-xs font-medium text-muted-foreground hover:text-foreground"
                onClick={() => {
                  clearParticipantProfile();
                  setParticipant(null);
                  setProfileReady(false);
                }}
              >
                Đổi người
              </button>
            </div>
          )}

          {/* Hướng dẫn được đóng gói gọn gàng */}
          <div className="mt-10 rounded-2xl border border-border/60 bg-muted/30 p-6 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Hướng dẫn
            </p>
            <ol className="mt-4 space-y-3 text-sm leading-relaxed text-muted-foreground">
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 font-medium text-primary">
                  1
                </span>
                <span>
                  Liệt kê càng nhiều cách dùng khác công dụng thông thường càng
                  tốt.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 font-medium text-primary">
                  2
                </span>
                <span>
                  Viết tự do — gạch đầu dòng, viết hoa thường, sai chính tả đều
                  được. AI sẽ tự hiểu.
                </span>
              </li>
            </ol>
          </div>
        </aside>

        {/* Cột phải: Khu vực nhập liệu (Focus chính) */}
        <div className="flex flex-col">
          <div className="flex items-baseline justify-between gap-4">
            <label
              className="font-serif text-xl text-foreground"
              htmlFor="aut-input"
            >
              Các cách dùng bạn nghĩ ra
            </label>
            <span className="rounded-md bg-muted px-2 py-1 font-mono text-xs text-muted-foreground tabular-nums">
              {wordCount} từ · {charCount} ký tự
            </span>
          </div>

          <Textarea
            id="aut-input"
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={submitting}
            placeholder="Ví dụ:- Làm que đo độ sâu chậu nước; Gõ tạo nhịp khi nấu cơm; Ghim tóc tạm thời; Làm cọc cắm hoa nhỏ..."
            className="mt-5 min-h-[400px] resize-y rounded-xl border-border/80 bg-card/50 p-5 font-sans text-base leading-8 shadow-sm transition-all focus-visible:border-primary/50 focus-visible:ring-2 focus-visible:ring-primary/20"
          />

          {submitError && (
            <div className="mt-4 flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
              <span className="mt-0.5 text-lg">⚠️</span>
              <p>{submitError}</p>
            </div>
          )}

          {/* Action Area */}
          <div className="mt-8 flex flex-col-reverse items-stretch justify-between gap-4 rounded-xl border border-border/60 bg-muted/20 p-5 md:flex-row md:items-center">
            <p className="text-xs leading-relaxed text-muted-foreground">
              Khi bấm <strong className="text-foreground">Nộp bài</strong>, hệ
              thống AI sẽ chuẩn hoá ý tưởng, đối chiếu mã và chấm 4 tiêu chí
              sáng tạo.
            </p>

            <Button
              size="lg"
              disabled={!isReadyToSubmit}
              onClick={handleSubmit}
              className={cn(
                "w-full transition-all md:w-auto md:min-w-[200px]",
                isReadyToSubmit &&
                  "shadow-lg shadow-primary/20 hover:shadow-primary/30",
              )}
            >
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Đang phân tích...
                </>
              ) : (
                <>
                  Nộp bài
                  <Send className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                </>
              )}
            </Button>
          </div>
        </div>
      </section>
      )}
    </div>
  );
}
