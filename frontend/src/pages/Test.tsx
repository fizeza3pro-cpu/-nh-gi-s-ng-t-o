import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Loader2, Pause, Play, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { api, cacheResponse } from "@/lib/api";
import { cn, formatMmSs } from "@/lib/utils";
import type { Item } from "@/lib/types";

const TOTAL_SECONDS = 180;

export default function Test() {
  const { itemId } = useParams<{ itemId: string }>();
  const navigate = useNavigate();

  const [item, setItem] = useState<Item | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [secondsLeft, setSecondsLeft] = useState(TOTAL_SECONDS);
  const [running, setRunning] = useState(false);
  const [started, setStarted] = useState(false);

  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load item
  useEffect(() => {
    if (!itemId) return;
    api
      .getItem(itemId)
      .then(setItem)
      .catch((err: Error) => setLoadError(err.message));
  }, [itemId]);

  // Timer tick
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          window.clearInterval(id);
          setRunning(false);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [running]);

  const startTimer = () => {
    setStarted(true);
    setRunning(true);
    setTimeout(() => textareaRef.current?.focus(), 60);
  };

  const handleSubmit = async () => {
    if (!itemId || !text.trim() || submitting) return;
    setSubmitError(null);
    setSubmitting(true);
    setRunning(false);
    try {
      const resp = await api.score(itemId, text);
      cacheResponse(resp);
      navigate(`/result/${resp.response_id}`);
    } catch (err) {
      setSubmitError((err as Error).message);
      setSubmitting(false);
    }
  };

  const charCount = text.length;
  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
  const lowTime = secondsLeft <= 30 && started;

  if (loadError) {
    return (
      <div className="container max-w-xl py-24 text-center">
        <p className="font-serif text-2xl">Không tải được đồ vật.</p>
        <p className="mt-2 text-muted-foreground">{loadError}</p>
        <Button asChild variant="outline" className="mt-6">
          <Link to="/">Quay lại trang chủ</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {/* Sub-header / status bar */}
      <div className="sticky top-16 z-20 border-b border-border/80 bg-background/95 backdrop-blur">
        <div className="container flex items-center justify-between gap-4 py-4">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Thoát bài test
          </Link>

          <div className="flex items-center gap-5">
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Thời gian còn lại
              </p>
              <p
                className={cn(
                  "font-mono text-2xl font-medium tabular-nums tracking-tight",
                  lowTime && secondsLeft > 0 && "text-destructive animate-pulse",
                  secondsLeft === 0 && "text-destructive",
                )}
              >
                {formatMmSs(secondsLeft)}
              </p>
            </div>
            {started ? (
              <Button
                variant="outline"
                size="icon"
                onClick={() => setRunning((r) => !r)}
                disabled={secondsLeft === 0 || submitting}
                aria-label={running ? "Tạm dừng" : "Tiếp tục"}
              >
                {running ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              </Button>
            ) : (
              <Button onClick={startTimer} disabled={!item}>
                Bắt đầu
              </Button>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-px w-full bg-border">
          <div
            className={cn(
              "h-px bg-foreground transition-all duration-1000 ease-linear",
              lowTime && "bg-destructive",
            )}
            style={{ width: `${(secondsLeft / TOTAL_SECONDS) * 100}%` }}
          />
        </div>
      </div>

      <section className="container grid gap-12 py-12 md:grid-cols-[1fr_2fr] md:py-16">
        {/* Object panel */}
        <aside className="md:sticky md:top-44 md:self-start">
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            Đồ vật
          </p>
          {item ? (
            <h1 className="mt-3 font-serif text-5xl font-medium tracking-tight md:text-6xl">
              {item.name}
            </h1>
          ) : (
            <Skeleton className="mt-3 h-14 w-40" />
          )}
          {item ? (
            <p className="mt-5 max-w-sm text-pretty text-muted-foreground">
              {item.description}
            </p>
          ) : (
            <Skeleton className="mt-5 h-12 w-full max-w-sm" />
          )}

          <div className="mt-10 rounded-xl border border-border bg-card/60 p-6">
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Hướng dẫn
            </p>
            <ol className="mt-3 space-y-2.5 text-sm leading-relaxed text-muted-foreground">
              <li>
                <span className="font-medium text-foreground">1.</span> Liệt kê
                càng nhiều cách dùng <em>khác công dụng thông thường</em> càng tốt.
              </li>
              <li>
                <span className="font-medium text-foreground">2.</span> Viết tự
                do — gạch đầu dòng, viết hoa thường, sai chính tả đều được.
              </li>
              <li>
                <span className="font-medium text-foreground">3.</span> AI sẽ
                tự tách ý, hiểu nghĩa, và gán danh mục trước khi chấm điểm.
              </li>
            </ol>
          </div>
        </aside>

        {/* Input area */}
        <div className="flex flex-col">
          <div className="flex items-baseline justify-between gap-4">
            <label className="font-serif text-lg" htmlFor="aut-input">
              Các cách dùng bạn nghĩ ra
            </label>
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {wordCount} từ · {charCount} ký tự
            </span>
          </div>

          <Textarea
            id="aut-input"
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={!started || submitting || secondsLeft === 0}
            placeholder={
              started
                ? "VD: làm que đo độ sâu chậu nước, gõ tạo nhịp khi nấu cơm, ghim tóc, làm cọc cắm hoa nhỏ..."
                : "Bấm “Bắt đầu” để khởi động đồng hồ và mở ô nhập."
            }
            className="mt-4 min-h-[340px] resize-y bg-card font-sans text-base leading-7"
          />

          {submitError && (
            <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {submitError}
            </p>
          )}

          <div className="mt-6 flex flex-col-reverse items-stretch justify-between gap-4 sm:flex-row sm:items-center">
            <p className="text-xs leading-relaxed text-muted-foreground">
              Khi bấm <strong className="text-foreground">Nộp bài</strong>, AI
              sẽ chạy 2 lượt: chuẩn hoá ý tưởng, sau đó chấm Fluency · Flexibility
              · Originality · Elaboration.
            </p>
            <Button
              size="lg"
              disabled={!text.trim() || submitting || !started}
              onClick={handleSubmit}
              className="sm:min-w-[180px]"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Đang chấm…
                </>
              ) : (
                <>
                  Nộp bài
                  <Send className="h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
