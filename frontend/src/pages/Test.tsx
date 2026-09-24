import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, Lightbulb, Loader2, Send } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ParticipantProfileForm from "@/components/participant/ParticipantProfileForm";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  cacheResponse,
  clearParticipantProfile,
  getParticipantIdentity,
  hasParticipantProfile,
} from "@/lib/api";
import type { Item, ParticipantIdentity } from "@/lib/types";

const IDEA_LIMIT = 10;

export default function Test() {
  const { itemId } = useParams<{ itemId: string }>();
  const navigate = useNavigate();
  const [item, setItem] = useState<Item | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [ideas, setIdeas] = useState<string[]>(() => Array(IDEA_LIMIT).fill(""));
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [profileReady, setProfileReady] = useState(hasParticipantProfile);
  const [participant, setParticipant] = useState<ParticipantIdentity | null>(getParticipantIdentity);
  const inputs = useRef<Array<HTMLTextAreaElement | null>>([]);

  useEffect(() => {
    if (!itemId) return;
    api.getItem(itemId).then(setItem).catch((error: Error) => setLoadError(error.message));
  }, [itemId]);

  useEffect(() => {
    if (!item || !profileReady) return;
    const timer = window.setTimeout(
      () => inputs.current[0]?.focus({ preventScroll: true }),
      180,
    );
    return () => window.clearTimeout(timer);
  }, [item, profileReady]);

  const completedIdeas = useMemo(
    () => ideas.map((idea) => idea.trim()).filter(Boolean),
    [ideas],
  );

  const updateIdea = (index: number, value: string) => {
    setIdeas((current) => current.map((idea, ideaIndex) => ideaIndex === index ? value : idea));
  };

  const resizeIdeaInput = (target: HTMLTextAreaElement) => {
    target.style.height = "auto";
    const nextHeight = Math.min(target.scrollHeight, 112);
    target.style.height = `${Math.max(nextHeight, 48)}px`;
    target.style.overflowY = target.scrollHeight > 112 ? "auto" : "hidden";
  };

  const handlePaste = (index: number, event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pastedLines = event.clipboardData.getData("text").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (pastedLines.length <= 1) return;
    event.preventDefault();
    setIdeas((current) => {
      const next = [...current];
      pastedLines.slice(0, IDEA_LIMIT - index).forEach((line, offset) => {
        next[index + offset] = line.replace(/^[-•\d.)\s]+/, "").trim();
      });
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!itemId || completedIdeas.length === 0 || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await api.score(itemId, completedIdeas);
      cacheResponse(response);
      navigate(`/result/${response.response_id}`, { state: { response } });
    } catch (error) {
      const message = (error as Error).message;
      if (message.includes("hồ sơ người tham gia")) {
        clearParticipantProfile();
        setParticipant(null);
        setProfileReady(false);
      }
      setSubmitError(message);
      setSubmitting(false);
    }
  };

  if (loadError) {
    return (
      <div className="container flex min-h-[60vh] max-w-xl flex-col items-center justify-center py-24 text-center">
        <p className="font-serif text-2xl text-destructive">Không tải được dữ liệu.</p>
        <p className="mt-2 text-muted-foreground">{loadError}</p>
        <Button asChild variant="outline" className="mt-6"><Link to="/">Quay lại trang chủ</Link></Button>
      </div>
    );
  }

  if (!profileReady) {
    return (
      <div className="container py-10 md:py-16">
        <ParticipantProfileForm onComplete={(identity) => {
          setParticipant(identity);
          setProfileReady(true);
        }} />
      </div>
    );
  }

  return (
    <div className="min-h-screen animate-fade-in bg-background">
      <section className="relative overflow-hidden border-b border-border bg-foreground text-background">
        <div className="pointer-events-none absolute inset-y-0 right-[12%] hidden w-px bg-background/10 lg:block" aria-hidden />
        <div className="container relative grid gap-8 py-10 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-end lg:py-14">
          <div>
            <Link to="/" className="inline-flex items-center gap-2 rounded-md px-1 py-1 text-sm text-background/65 transition-colors hover:text-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-background/50">
              <ArrowLeft className="h-4 w-4" /> Chọn đồ vật khác
            </Link>
            <p className="mt-8 text-sm text-[#D7B899]">Bài tập tạo công dụng thay thế</p>
            {item ? (
              <h1 className="mt-2 font-serif text-5xl leading-none md:text-6xl">{item.name}</h1>
            ) : <Skeleton className="mt-2 h-16 w-52 bg-background/15" />}
            <p className="mt-5 max-w-2xl text-base leading-7 text-background/70">
              Mỗi ô dành cho một ý tưởng độc lập. Hãy mô tả công dụng đủ rõ để người khác hiểu đồ vật được dùng như thế nào.
            </p>
          </div>
          <div className="rounded-xl border border-background/15 bg-background/[0.04] p-5 shadow-[0_18px_50px_-32px_rgba(0,0,0,0.8)] backdrop-blur-sm lg:p-6">
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-sm leading-6 text-background/65">Đã nhập</p>
                <p className="mt-1 font-serif text-5xl tabular-nums">{completedIdeas.length}<span className="text-2xl text-background/35">/{IDEA_LIMIT}</span></p>
              </div>
              <p className="pb-1 text-xs text-background/50">Không cần điền đủ</p>
            </div>
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-background/15">
              <div className="h-full rounded-full bg-[#C89562] transition-[width] duration-500 ease-out motion-reduce:transition-none" style={{ width: `${completedIdeas.length * 10}%` }} />
            </div>
          </div>
        </div>
      </section>

      <section className="container grid gap-8 py-8 lg:grid-cols-[minmax(0,1fr)_19rem] lg:py-12">
        <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_1px_0_hsl(var(--border)),0_28px_70px_-48px_rgba(56,39,30,0.55)]">
          <div className="flex items-center justify-between border-b border-border bg-muted/20 px-5 py-5 md:px-7">
            <div>
              <h2 className="font-serif text-2xl text-foreground">Sổ ý tưởng</h2>
              <p className="mt-1 text-sm text-muted-foreground">Mỗi ô ghi một công dụng độc lập.</p>
            </div>
            <span className="grid h-10 w-10 place-items-center rounded-full border border-[#8B5E34]/20 bg-[#8B5E34]/[0.07]">
              <Lightbulb className="h-5 w-5 text-[#8B5E34]" />
            </span>
          </div>

          <div className="space-y-3 p-4 md:p-6">
            {ideas.map((idea, index) => {
              const filled = Boolean(idea.trim());
              return (
                <label
                  key={index}
                  className={`group grid grid-cols-[2.5rem_minmax(0,1fr)_1.5rem] items-start gap-3 rounded-xl border px-3 py-2.5 shadow-[0_5px_16px_-13px_rgba(56,39,30,0.6)] transition-[transform,border-color,box-shadow,background-color] duration-200 focus-within:-translate-y-0.5 focus-within:border-[#8B5E34]/55 focus-within:bg-white focus-within:shadow-[0_14px_30px_-18px_rgba(75,50,37,0.45)] focus-within:ring-2 focus-within:ring-[#8B5E34]/10 motion-reduce:transform-none motion-reduce:transition-none md:grid-cols-[3rem_minmax(0,1fr)_1.5rem] md:px-4 ${filled ? "border-[#8B5E34]/30 bg-[#FBF8F4]" : "border-border bg-card hover:border-[#8B5E34]/25 hover:shadow-[0_8px_22px_-16px_rgba(56,39,30,0.45)]"}`}
                >
                  <span className={`mt-1.5 grid h-8 w-8 place-items-center rounded-lg font-mono text-xs transition-colors duration-200 motion-reduce:transition-none ${filled ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground group-focus-within:bg-[#8B5E34] group-focus-within:text-white"}`}>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <textarea
                    ref={(node) => { inputs.current[index] = node; }}
                    value={idea}
                    disabled={submitting}
                    rows={1}
                    maxLength={320}
                    onChange={(event) => updateIdea(index, event.target.value)}
                    onInput={(event) => resizeIdeaInput(event.currentTarget)}
                    onPaste={(event) => handlePaste(index, event)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        inputs.current[Math.min(index + 1, IDEA_LIMIT - 1)]?.focus();
                      }
                    }}
                    aria-label={`Ý tưởng ${index + 1}`}
                    placeholder={index === 0 ? "Ví dụ: Làm vật giữ cửa" : "Một công dụng khác"}
                    className="min-h-12 w-full resize-none overflow-hidden bg-transparent py-2.5 text-[15px] leading-6 text-foreground outline-none placeholder:text-muted-foreground/55 disabled:cursor-wait disabled:opacity-60"
                  />
                  <span className="grid h-12 place-items-center">
                    {filled && <CheckCircle2 className="h-4 w-4 animate-in zoom-in-75 text-[#8B5E34] duration-200 motion-reduce:animate-none" />}
                  </span>
                </label>
              );
            })}
          </div>
        </div>

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="rounded-xl border border-border bg-card p-5 shadow-[0_16px_38px_-30px_rgba(56,39,30,0.5)]">
            <h2 className="font-serif text-xl text-foreground">Trước khi gửi</h2>
            <ul className="mt-4 space-y-3 text-sm leading-6 text-muted-foreground">
              <li className="border-l-2 border-[#8B5E34]/35 pl-3">Mỗi ô chỉ trình bày một công dụng chính.</li>
              <li className="border-l-2 border-[#8B5E34]/35 pl-3">Có thể cắt, ghép hoặc biến đổi đồ vật.</li>
              <li className="border-l-2 border-[#8B5E34]/35 pl-3">Nhấn Enter để chuyển nhanh sang ô tiếp theo.</li>
            </ul>
            {participant?.full_name && (
              <p className="mt-5 border-t border-border pt-4 text-xs text-muted-foreground">Người làm bài: <span className="font-medium text-foreground">{participant.full_name}</span></p>
            )}
          </div>

          {submitError && <p className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-700 shadow-sm">{submitError}</p>}

          <Button
            size="lg"
            disabled={completedIdeas.length === 0 || submitting}
            onClick={handleSubmit}
            className="mt-4 h-14 w-full rounded-xl shadow-[0_14px_26px_-16px_hsl(var(--primary)/0.85)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-0.5 hover:shadow-[0_18px_34px_-17px_hsl(var(--primary)/0.8)] active:translate-y-0 motion-reduce:transform-none motion-reduce:transition-none"
          >
            {submitting ? <><Loader2 className="h-4 w-4 animate-spin" /> Đang phân tích</> : <><Send className="h-4 w-4" /> Gửi {completedIdeas.length} ý tưởng</>}
          </Button>
          <p className="mt-3 text-center text-xs leading-5 text-muted-foreground">Kết quả được tính ngay sau khi hệ thống đối chiếu sổ mã.</p>
        </aside>
      </section>
    </div>
  );
}
