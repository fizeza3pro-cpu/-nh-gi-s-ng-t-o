import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Clock3,
  HelpCircle,
  Lightbulb,
  ListChecks,
  Loader2,
  Play,
  Send,
  Sparkles,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import ParticipantProfileForm from "@/components/participant/ParticipantProfileForm";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  cacheResponse,
  clearParticipantProfile,
  getParticipantIdentity,
  hasParticipantProfile,
} from "@/lib/api";
import { responseNeedsProcessing } from "@/lib/response-status";
import { readDraft, saveDraft, clearDraft } from "@/lib/survey-draft";
import type { Item, ParticipantIdentity, ScoreResponse } from "@/lib/types";
import { formatMmSs } from "@/lib/utils";

const IDEA_LIMIT = 10;
const TEST_DURATION_SECONDS = 180;
const GUIDE_STORAGE_KEY = "aut:test-guide-seen:v1";
const SUBMISSION_POLL_TIMEOUT_MS = 180_000;

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

async function waitForCompletedResponse(
  initialResponse: ScoreResponse,
): Promise<ScoreResponse> {
  let latest = initialResponse;
  let delay = 750;
  const deadline = Date.now() + SUBMISSION_POLL_TIMEOUT_MS;

  while (responseNeedsProcessing(latest)) {
    if (Date.now() >= deadline) {
      throw new Error(
        "Bài đã được lưu nhưng hệ thống cần thêm thời gian xử lý. Bạn có thể thử gửi lại để tiếp tục kiểm tra trạng thái.",
      );
    }
    await wait(delay);
    latest = await api.getResponse(initialResponse.response_id);
    cacheResponse(latest);
    delay = Math.min(Math.round(delay * 1.35), 4_000);
  }

  return latest;
}

const loadAiThinkingAnimation = () =>
  import("@/components/AiThinkingAnimation");
const AiThinkingAnimation = lazy(loadAiThinkingAnimation);

const GUIDE_STEPS = [
  {
    icon: Clock3,
    title: "Nhấn bắt đầu",
    body: "Đồng hồ 03:00 chỉ chạy khi bạn chủ động bắt đầu.",
  },
  {
    icon: ListChecks,
    title: "Mỗi ô một ý",
    body: "Viết một công dụng rõ ràng trong từng ô, tối đa 10 ý.",
  },
  {
    icon: Sparkles,
    title: "Tìm cách dùng khác",
    body: "Có thể cắt, ghép, biến đổi hoặc dùng đồ vật trong bối cảnh mới.",
  },
] as const;

type TestPhase = "READY" | "ACTIVE" | "EXPIRED";

const ANALYSIS_STEPS = [
  "Đọc và tách từng ý tưởng",
  "Làm rõ ý nghĩa câu trả lời",
  "Đối chiếu các nhóm công dụng",
  "Tổng hợp kết quả nghiên cứu",
] as const;

export default function Test() {
  const { itemId } = useParams<{ itemId: string }>();
  const navigate = useNavigate();
  const [draft] = useState(() => (itemId ? readDraft(itemId) : null));
  const [item, setItem] = useState<Item | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [ideas, setIdeas] = useState<string[]>(
    () => draft?.ideas ?? Array(IDEA_LIMIT).fill(""),
  );
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [profileReady, setProfileReady] = useState(hasParticipantProfile);
  const [participant, setParticipant] = useState<ParticipantIdentity | null>(
    getParticipantIdentity,
  );
  const [phase, setPhase] = useState<TestPhase>(draft ? "ACTIVE" : "READY");
  const [secondsLeft, setSecondsLeft] = useState(TEST_DURATION_SECONDS);
  const [guideOpen, setGuideOpen] = useState(
    () => localStorage.getItem(GUIDE_STORAGE_KEY) !== "true",
  );
  const inputs = useRef<Array<HTMLTextAreaElement | null>>([]);
  const deadlineRef = useRef<number | null>(draft?.deadline ?? null);
  const sessionIdRef = useRef<string | null>(draft?.sessionId ?? null);
  const completedIdeasRef = useRef<string[]>([]);
  const submittedRef = useRef(false);
  const requestIdRef = useRef<string | null>(draft?.requestId ?? null);

  useEffect(() => {
    if (!itemId) return;
    api
      .getItem(itemId)
      .then(setItem)
      .catch((error: Error) => setLoadError(error.message));
  }, [itemId]);

  const completedIdeas = useMemo(
    () => ideas.map((idea) => idea.trim()).filter(Boolean),
    [ideas],
  );

  useEffect(() => {
    completedIdeasRef.current = completedIdeas;
  }, [completedIdeas]);

  useEffect(() => {
    if (
      itemId &&
      sessionIdRef.current &&
      deadlineRef.current &&
      requestIdRef.current
    ) {
      if (
        !saveDraft(itemId, {
          ideas,
          deadline: deadlineRef.current,
          sessionId: sessionIdRef.current,
          requestId: requestIdRef.current,
        })
      ) {
        setSubmitError(
          "Trình duyệt không lưu được bản nháp. Hãy giữ trang này mở cho đến khi gửi bài.",
        );
      }
    }
  }, [ideas, itemId, phase]);

  const submitAnswers = useCallback(async () => {
    const answers = completedIdeasRef.current;
    if (!itemId || answers.length === 0 || submittedRef.current) return;

    submittedRef.current = true;
    setSubmitting(true);
    setSubmitError(null);
    try {
      requestIdRef.current ??= crypto.randomUUID();
      const acceptedResponse = await api.score(
        itemId,
        answers,
        requestIdRef.current,
        sessionIdRef.current ?? undefined,
      );
      cacheResponse(acceptedResponse);
      const response = await waitForCompletedResponse(acceptedResponse);
      cacheResponse(response);
      clearDraft(itemId);
      navigate(`/result/${response.response_id}`, {
        state: { response, source: "submission" },
      });
    } catch (error) {
      const message = (error as Error).message;
      if (message.includes("hồ sơ người tham gia")) {
        clearParticipantProfile();
        setParticipant(null);
        setProfileReady(false);
      }
      setSubmitError(`${message} Hãy kiểm tra kết nối rồi gửi lại.`);
      submittedRef.current = false;
      setSubmitting(false);
    }
  }, [itemId, navigate]);

  useEffect(() => {
    if (phase !== "ACTIVE" || submitting || !deadlineRef.current) return;

    const updateTimer = () => {
      const remaining = Math.max(
        0,
        Math.ceil((deadlineRef.current! - Date.now()) / 1000),
      );
      setSecondsLeft(remaining);
      if (remaining === 0) {
        setPhase("EXPIRED");
        if (completedIdeasRef.current.length > 0) void submitAnswers();
      }
    };

    updateTimer();
    const timer = window.setInterval(updateTimer, 250);
    return () => window.clearInterval(timer);
  }, [phase, submitAnswers, submitting]);

  useEffect(() => {
    if (phase !== "ACTIVE" || completedIdeas.length === 0) return;
    const warnBeforeLeaving = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warnBeforeLeaving);
    return () => window.removeEventListener("beforeunload", warnBeforeLeaving);
  }, [completedIdeas.length, phase]);

  const closeGuide = useCallback(() => {
    localStorage.setItem(GUIDE_STORAGE_KEY, "true");
    setGuideOpen(false);
  }, []);

  const startTest = async () => {
    if (!itemId || starting) return;
    setStarting(true);
    try {
      const session = await api.startSurveySession(itemId);
      void loadAiThinkingAnimation();
      deadlineRef.current =
        Date.now() +
        (Date.parse(session.deadline_at) - Date.parse(session.server_now));
      sessionIdRef.current = session.id;
      requestIdRef.current = crypto.randomUUID();
      setSecondsLeft(TEST_DURATION_SECONDS);
      setSubmitError(null);
      setPhase("ACTIVE");
      window.setTimeout(
        () => inputs.current[0]?.focus({ preventScroll: true }),
        120,
      );
    } catch (error) {
      setSubmitError((error as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const resetTest = () => {
    if (itemId) clearDraft(itemId);
    sessionIdRef.current = null;
    deadlineRef.current = null;
    setIdeas(Array(IDEA_LIMIT).fill(""));
    setSecondsLeft(TEST_DURATION_SECONDS);
    setSubmitError(null);
    submittedRef.current = false;
    requestIdRef.current = null;
    setPhase("READY");
  };

  const updateIdea = (index: number, value: string) => {
    setIdeas((current) =>
      current.map((idea, ideaIndex) => (ideaIndex === index ? value : idea)),
    );
  };

  const resizeIdeaInput = (target: HTMLTextAreaElement) => {
    target.style.height = "auto";
    const nextHeight = Math.min(target.scrollHeight, 112);
    target.style.height = `${Math.max(nextHeight, 48)}px`;
    target.style.overflowY = target.scrollHeight > 112 ? "auto" : "hidden";
  };

  const confirmExit = (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (
      phase === "ACTIVE" &&
      completedIdeas.length > 0 &&
      !window.confirm(
        "Rời bài làm? Đồng hồ vẫn tiếp tục chạy; bản nháp chỉ được giữ trên trình duyệt này.",
      )
    ) {
      event.preventDefault();
    }
  };

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

  if (!profileReady) {
    return (
      <div className="container py-10 md:py-16">
        <ParticipantProfileForm
          onComplete={(identity) => {
            setParticipant(identity);
            setProfileReady(true);
          }}
        />
      </div>
    );
  }

  const timerUrgent = phase === "ACTIVE" && secondsLeft <= 30;
  const timerProgress = (secondsLeft / TEST_DURATION_SECONDS) * 100;

  return (
    <div className="min-h-screen animate-fade-in bg-background">
      <section className="relative overflow-hidden border-b border-border bg-foreground text-background">
        <div
          className="pointer-events-none absolute inset-y-0 right-[12%] hidden w-px bg-background/10 lg:block"
          aria-hidden="true"
        />
        <div className="container relative grid gap-8 py-9 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-end lg:py-12">
          <div>
            <Link
              to="/"
              onClick={confirmExit}
              className="inline-flex items-center gap-2 rounded-md px-1 py-1 text-sm text-background/65 transition-colors hover:text-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-background/50"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Chọn đồ vật
              khác
            </Link>

            {item ? (
              <h1 className="mt-10 text-balance font-serif text-5xl leading-none md:text-6xl">
                {item.name}
              </h1>
            ) : (
              <Skeleton className="mt-2 h-16 w-52 bg-background/15" />
            )}
            <p className="mt-5 max-w-2xl text-pretty text-base leading-7 text-background/70">
              Viết mỗi công dụng trong một ô. Đồng hồ chỉ chạy sau khi bạn nhấn
              bắt đầu.
            </p>
          </div>

          <div className="rounded-xl border border-background/15 bg-background/[0.04] p-5 shadow-[0_18px_50px_-32px_rgba(0,0,0,0.8)] backdrop-blur-sm lg:p-6">
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-sm leading-6 text-background/65">
                  {phase === "READY"
                    ? "Thời gian làm bài"
                    : phase === "ACTIVE"
                      ? "Thời gian còn lại"
                      : "Đã hết giờ"}
                </p>
                <p
                  className={`mt-1 font-mono text-5xl tabular-nums ${timerUrgent ? "text-amber-300" : "text-background"}`}
                  aria-label={`${secondsLeft} giây còn lại`}
                >
                  {formatMmSs(secondsLeft)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setGuideOpen(true)}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-background/15 px-3 text-sm text-background/75 transition-colors hover:bg-background/10 hover:text-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-background/60"
              >
                <HelpCircle className="h-4 w-4" aria-hidden="true" /> Hướng dẫn
              </button>
            </div>
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-background/15">
              <div
                className={`h-full origin-left rounded-full transition-[width,background-color] duration-300 motion-reduce:transition-none ${timerUrgent ? "bg-amber-300" : "bg-research-bright"}`}
                style={{ width: `${timerProgress}%` }}
              />
            </div>
          </div>
        </div>
      </section>

      {phase === "READY" ? (
        <ReadyPanel
          itemName={item?.name}
          participantName={participant?.full_name}
          onStart={startTest}
          starting={starting}
          error={submitError}
          recoveryToken={participant?.access_token}
          onOpenGuide={() => setGuideOpen(true)}
        />
      ) : (
        <section className="container grid gap-8 py-8 lg:grid-cols-[minmax(0,1fr)_19rem] lg:py-12">
          <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_1px_0_hsl(var(--border)),0_28px_70px_-48px_rgba(56,39,30,0.55)]">
            <div className="flex items-center justify-between border-b border-border bg-muted/20 px-5 py-5 md:px-7">
              <div>
                <h2 className="font-serif text-2xl text-foreground">
                  Sổ ý tưởng
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Đã viết {completedIdeas.length}/{IDEA_LIMIT} ý. Không cần điền
                  đủ.
                </p>
              </div>
              <span className="grid h-10 w-10 place-items-center rounded-full border border-research/20 bg-research-soft">
                <Lightbulb
                  className="h-5 w-5 text-research"
                  aria-hidden="true"
                />
              </span>
            </div>

            <div className="space-y-3 p-4 md:p-6">
              {ideas.map((idea, index) => {
                const filled = Boolean(idea.trim());
                return (
                  <label
                    key={index}
                    className={`group grid grid-cols-[2.5rem_minmax(0,1fr)_1.5rem] items-start gap-3 rounded-xl border px-3 py-2.5 shadow-[0_5px_16px_-13px_rgba(56,39,30,0.6)] transition-[transform,border-color,box-shadow,background-color] duration-200 focus-within:-translate-y-0.5 focus-within:border-research/55 focus-within:bg-white focus-within:shadow-[0_14px_30px_-18px_rgba(75,50,37,0.45)] focus-within:ring-2 focus-within:ring-research/10 motion-reduce:transform-none motion-reduce:transition-none md:grid-cols-[3rem_minmax(0,1fr)_1.5rem] md:px-4 ${filled ? "border-research/30 bg-research-soft/60" : "border-border bg-card hover:border-research/25"}`}
                  >
                    <span
                      className={`mt-1.5 grid h-8 w-8 place-items-center rounded-lg font-mono text-xs transition-colors ${filled ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground group-focus-within:bg-research group-focus-within:text-research-foreground"}`}
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <textarea
                      ref={(node) => {
                        inputs.current[index] = node;
                      }}
                      value={idea}
                      disabled={submitting || phase !== "ACTIVE"}
                      rows={1}
                      maxLength={320}
                      onChange={(event) =>
                        updateIdea(index, event.target.value)
                      }
                      onInput={(event) => resizeIdeaInput(event.currentTarget)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          inputs.current[
                            Math.min(index + 1, IDEA_LIMIT - 1)
                          ]?.focus();
                        }
                      }}
                      aria-label={`Ý tưởng ${index + 1}`}
                      placeholder={
                        index === 0
                          ? "Ví dụ: Dùng làm vật giữ cửa…"
                          : "Một công dụng khác…"
                      }
                      className="min-h-12 w-full resize-none overflow-hidden bg-transparent py-2.5 text-base leading-6 text-foreground outline-none placeholder:text-muted-foreground/55 disabled:cursor-not-allowed disabled:opacity-60 sm:text-[15px]"
                    />
                    <span
                      className="grid h-12 place-items-center"
                      aria-hidden="true"
                    >
                      {filled ? (
                        <CheckCircle2 className="h-4 w-4 text-research" />
                      ) : null}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <aside className="lg:sticky lg:top-24 lg:self-start">
            <div className="rounded-xl border border-border bg-card p-5 shadow-[0_16px_38px_-30px_rgba(56,39,30,0.5)]">
              <h2 className="font-serif text-xl text-foreground">
                {phase === "EXPIRED"
                  ? "Thời gian đã kết thúc"
                  : "Trong khi làm bài"}
              </h2>
              {phase === "EXPIRED" ? (
                <p
                  className="mt-3 text-sm leading-6 text-muted-foreground"
                  aria-live="polite"
                >
                  {completedIdeas.length > 0
                    ? "Hệ thống đang gửi các ý tưởng bạn đã hoàn thành."
                    : "Bạn chưa ghi ý tưởng nào nên bài chưa được gửi."}
                </p>
              ) : (
                <ul className="mt-4 space-y-3 text-sm leading-6 text-muted-foreground">
                  <li className="border-l-2 border-research/35 pl-3">
                    Mỗi ô chỉ trình bày một công dụng chính.
                  </li>
                  <li className="border-l-2 border-research/35 pl-3">
                    Ưu tiên ý tưởng khác với cách dùng thông thường.
                  </li>
                  <li className="border-l-2 border-research/35 pl-3">
                    Nhấn Enter để chuyển nhanh sang ô tiếp theo.
                  </li>
                </ul>
              )}
              {participant?.full_name ? (
                <p className="mt-5 border-t border-border pt-4 text-xs text-muted-foreground">
                  Người làm bài:{" "}
                  <span className="font-medium text-foreground">
                    {participant.full_name}
                  </span>
                </p>
              ) : null}
            </div>

            {submitError ? (
              <p
                role="alert"
                className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm leading-6 text-destructive"
              >
                {submitError}
              </p>
            ) : null}

            {phase === "EXPIRED" && completedIdeas.length === 0 ? (
              <Button
                size="lg"
                variant="outline"
                onClick={resetTest}
                className="mt-4 h-14 w-full rounded-xl"
              >
                Bắt đầu lại 3 phút
              </Button>
            ) : (
              <Button
                size="lg"
                disabled={completedIdeas.length === 0 || submitting}
                onClick={() => void submitAnswers()}
                onMouseEnter={() => void loadAiThinkingAnimation()}
                onFocus={() => void loadAiThinkingAnimation()}
                className="mt-4 h-14 w-full rounded-xl shadow-[0_14px_26px_-16px_hsl(var(--primary)/0.85)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-0.5 active:translate-y-0 motion-reduce:transform-none"
              >
                {submitting ? (
                  <>
                    <Loader2
                      className="h-4 w-4 animate-spin"
                      aria-hidden="true"
                    />{" "}
                    Đang gửi…
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" aria-hidden="true" /> Gửi{" "}
                    {completedIdeas.length} ý tưởng
                  </>
                )}
              </Button>
            )}
            <p className="mt-3 text-center text-xs leading-5 text-muted-foreground">
              Bài tự gửi khi đồng hồ về 00:00.
            </p>
          </aside>
        </section>
      )}

      <GuideDialog open={guideOpen} onClose={closeGuide} />
      {submitting ? <AnalysisOverlay /> : null}
    </div>
  );
}

function ReadyPanel({
  itemName,
  participantName,
  onStart,
  starting,
  error,
  recoveryToken,
  onOpenGuide,
}: {
  itemName?: string;
  participantName?: string | null;
  onStart: () => void;
  starting: boolean;
  error: string | null;
  recoveryToken?: string | null;
  onOpenGuide: () => void;
}) {
  const [consent, setConsent] = useState(false);
  return (
    <section className="container py-10 md:py-16">
      <div className="mx-auto grid max-w-5xl overflow-hidden rounded-2xl border border-border bg-card lg:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)]">
        <div className="p-6 sm:p-9 lg:p-11">
          <p className="inline-flex items-center gap-2 text-sm font-medium text-research">
            <Clock3 className="h-4 w-4" aria-hidden="true" /> Đồng hồ chưa chạy
          </p>
          <h2 className="mt-4 max-w-2xl text-balance font-serif text-3xl leading-tight sm:text-4xl">
            Bạn có 3 phút để chọn và viết tối đa 10 công dụng sáng tạo nhất cho{" "}
            {itemName ?? "đồ vật này"}.
          </h2>
          <p className="mt-4 max-w-xl text-pretty text-sm leading-6 text-muted-foreground">
            Không có đáp án duy nhất. Hãy viết rõ đồ vật được dùng vào việc gì;
            ý tưởng lạ nhưng có thể hiểu được thường có giá trị hơn một từ rời
            rạc.
          </p>

          <label className="mt-6 flex items-start gap-3 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
              className="mt-1"
            />
            <span>
              Tôi đồng ý tham gia nghiên cứu. Câu trả lời được gửi đến dịch vụ
              AI để phân loại; tôi có thể liên hệ nhóm nghiên cứu để yêu cầu rút
              dữ liệu.
            </span>
          </label>
          {error ? (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button
              size="lg"
              onClick={onStart}
              disabled={!consent || starting}
              className="sm:min-w-52"
            >
              <Play className="h-4 w-4" aria-hidden="true" /> Bắt đầu 3 phút
            </Button>
            <Button size="lg" variant="outline" onClick={onOpenGuide}>
              <HelpCircle className="h-4 w-4" aria-hidden="true" /> Xem hướng
              dẫn
            </Button>
          </div>
          {participantName ? (
            <p className="mt-6 text-xs text-muted-foreground">
              Bài làm của {participantName}
            </p>
          ) : null}
          {recoveryToken ? (
            <details className="mt-3 text-xs text-muted-foreground">
              <summary className="cursor-pointer">
                Mã khôi phục hồ sơ — giữ riêng để dùng trên thiết bị khác
              </summary>
              <p className="mt-2 break-all font-mono">{recoveryToken}</p>
            </details>
          ) : null}
        </div>

        <div className="border-t border-border bg-muted/25 p-6 sm:p-9 lg:border-l lg:border-t-0">
          <p className="font-serif text-xl">Ghi nhớ trước khi bắt đầu</p>
          <ol className="mt-6 space-y-5">
            {[
              "Mỗi ô là một công dụng độc lập.",
              "Mô tả đủ rõ để người khác hình dung được.",
              "Bài tự gửi khi hết 3 phút nếu đã có câu trả lời.",
            ].map((text, index) => (
              <li
                key={text}
                className="flex gap-3 text-sm leading-6 text-muted-foreground"
              >
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-research/25 bg-research-soft font-mono text-xs text-research">
                  {index + 1}
                </span>
                <span className="pt-0.5">{text}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function GuideDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Cách làm bài trong 3 phút"
      description="Bạn không cần chuẩn bị đáp án trước. Hãy hiểu nguyên tắc, sau đó để ý tưởng xuất hiện tự nhiên."
      footer={
        <Button onClick={onClose} className="w-full sm:w-auto">
          Đã hiểu, tôi sẵn sàng
        </Button>
      }
    >
      <ol className="grid gap-2 sm:grid-cols-3 sm:gap-3">
        {GUIDE_STEPS.map(({ icon: Icon, title, body }, index) => (
          <li
            key={title}
            className="flex gap-3 rounded-xl border border-border bg-background p-3.5 sm:block sm:p-4"
          >
            <div className="flex shrink-0 items-start justify-between sm:items-center">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-research-soft text-research">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
                0{index + 1}
              </span>
            </div>
            <div className="min-w-0">
              <h3 className="font-serif text-lg sm:mt-5">{title}</h3>
              <p className="mt-1 text-sm leading-5 text-muted-foreground sm:mt-2 sm:leading-6">
                {body}
              </p>
            </div>
          </li>
        ))}
      </ol>

      <div className="mt-5 rounded-xl border border-research/20 bg-research-soft/60 p-5">
        <p className="text-xs font-medium text-research">
          Ví dụ với một chiếc cốc giấy
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <p className="rounded-lg bg-card px-4 py-3 text-sm text-muted-foreground line-through decoration-destructive/60">
            “Đựng nước” — cách dùng thông thường
          </p>
          <p className="rounded-lg border border-research/20 bg-card px-4 py-3 text-sm font-medium">
            “Cắt đáy để làm loa khuếch đại cho điện thoại”
          </p>
        </div>
      </div>
    </Dialog>
  );
}

function AnalysisOverlay() {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setActiveStep((step) => Math.min(step + 1, ANALYSIS_STEPS.length - 1));
    }, 1500);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    overlayRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []);

  return (
    <div
      ref={overlayRef}
      tabIndex={-1}
      className="fixed inset-0 z-[60] grid place-items-center bg-foreground/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-title"
      aria-describedby="analysis-description"
      onKeyDown={(event) => {
        if (event.key === "Tab") event.preventDefault();
      }}
    >
      <div className="w-full max-w-xl overflow-hidden rounded-2xl border border-background/20 bg-card shadow-[0_24px_64px_-24px_rgba(0,0,0,0.72)]">
        <div className="thinking-stage border-b border-border px-6 pb-7 pt-5 text-center sm:px-8 sm:pb-8">
          <Suspense
            fallback={
              <div
                className="mx-auto grid h-36 w-36 place-items-center"
                aria-hidden="true"
              >
                <span className="h-8 w-8 rounded-full border border-research/20 bg-research-soft motion-safe:animate-pulse" />
              </div>
            }
          >
            <AiThinkingAnimation />
          </Suspense>
          <h2
            id="analysis-title"
            className="font-serif text-2xl sm:text-[1.75rem]"
          >
            AI đang phân tích bài làm
          </h2>
          <p
            id="analysis-description"
            className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground"
          >
            Bài đã được lưu. Bạn có thể đóng trang; hệ thống vẫn tiếp tục xử lý
            và lưu kết quả vào lịch sử.
          </p>
        </div>

        <div className="px-6 py-6 sm:px-8">
          <ol className="space-y-3" aria-live="polite">
            {ANALYSIS_STEPS.map((label, index) => {
              const complete = index < activeStep;
              const active = index === activeStep;
              return (
                <li
                  key={label}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-[background-color,color,opacity] ${active ? "bg-research-soft text-foreground" : complete ? "text-muted-foreground" : "text-muted-foreground/45"}`}
                >
                  <span
                    className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border ${complete ? "border-research bg-research text-research-foreground" : active ? "border-research" : "border-border"}`}
                  >
                    {complete ? (
                      <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    ) : active ? (
                      <span
                        className="h-2 w-2 animate-pulse rounded-full bg-research motion-reduce:animate-none"
                        aria-hidden="true"
                      />
                    ) : null}
                  </span>
                  <span>
                    {label}
                    {active ? "…" : ""}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </div>
  );
}
