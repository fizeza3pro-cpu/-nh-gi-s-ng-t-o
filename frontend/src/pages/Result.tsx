import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ArrowRight, Clock3, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableViewport } from "@/components/ui/table";
import { api, cacheResponse, readCachedResponse } from "@/lib/api";
import { responseNeedsProcessing } from "@/lib/response-status";
import { cn } from "@/lib/utils";
import type { IdeaStatus, ScoreResponse } from "@/lib/types";

const AiThinkingAnimation = lazy(() => import("@/components/AiThinkingAnimation"));

type ResultNavigationState = {
  response?: ScoreResponse;
  source?: "submission" | "history";
};

function ResultThinkingPanel({
  loadingInitial = false,
  pollError = false,
  showAnimation,
  onRetry,
}: {
  loadingInitial?: boolean;
  pollError?: boolean;
  showAnimation: boolean;
  onRetry?: () => void;
}) {
  const title = pollError
    ? "Chưa kết nối được với hệ thống"
    : loadingInitial
      ? "Đang mở lại kết quả"
      : "AI đang phân tích bài làm";
  const description = pollError
    ? "Bài đã được lưu. Hãy kết nối lại để xem tiến độ; bạn không cần nộp lại bài."
    : loadingInitial
      ? "Hệ thống đang lấy trạng thái mới nhất của bài làm từ lịch sử."
      : "Bài đã được lưu. AI đang xử lý các ý tưởng của bạn, kết quả sẽ tự động xuất hiện khi hoàn tất.";

  return (
    <div className="container grid min-h-[70vh] max-w-xl place-items-center py-12">
      <section
        className="w-full overflow-hidden rounded-2xl border border-border bg-card text-center"
        aria-live="polite"
        aria-busy={!pollError}
      >
        <div className="thinking-stage px-6 py-8">
          {!pollError && showAnimation ? (
            <Suspense fallback={<div className="h-36" />}>
              <AiThinkingAnimation />
            </Suspense>
          ) : !pollError ? (
            <span className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-research-soft text-research">
              <Clock3 className="h-6 w-6" aria-hidden="true" />
            </span>
          ) : null}
          <h1 className={cn("font-serif text-3xl", !pollError && "mt-2")}>{title}</h1>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">{description}</p>
          {pollError && onRetry ? (
            <Button className="mt-5" onClick={onRetry}>Kết nối lại</Button>
          ) : null}
        </div>
      </section>
    </div>
  );
}

const STATUS_LABEL: Record<IdeaStatus, string> = {
  VALID: "Hợp lệ",
  INVALID: "Loại",
  DUPLICATE: "Trùng",
};

const STATUS_VARIANT: Record<IdeaStatus, "success" | "secondary" | "warning"> =
  {
    VALID: "success",
    INVALID: "secondary",
    DUPLICATE: "warning",
  };

export default function Result() {
  const { responseId } = useParams<{ responseId: string }>();
  const location = useLocation();
  const adminView = location.pathname.startsWith("/admin/responses/");
  const fetchResponse = adminView ? api.adminGetResponse : api.getResponse;
  const navigationState = location.state as ResultNavigationState | null;
  const navigatedResponse = navigationState?.response;
  const openedFromHistory = navigationState?.source === "history";
  const openedFromSubmission = navigationState?.source === "submission";
  const initialResponse =
    !openedFromHistory
      ? navigatedResponse ?? (responseId && !adminView ? readCachedResponse(responseId) : null)
      : null;
  const [resp, setResp] = useState<ScoreResponse | null>(() => initialResponse);
  const [loading, setLoading] = useState(() => !initialResponse);
  const [pollError, setPollError] = useState(false);
  const [pollAttempt, setPollAttempt] = useState(0);

  useEffect(() => {
    if (!responseId) {
      setLoading(false);
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = 1000;
    let failures = 0;
    setPollError(false);

    if (
      openedFromSubmission &&
      navigatedResponse &&
      !responseNeedsProcessing(navigatedResponse)
    ) {
      setResp(navigatedResponse);
      setLoading(false);
      return;
    }

    const immediate = navigatedResponse ?? (
      adminView || openedFromHistory ? null : readCachedResponse(responseId)
    );
    if (immediate) {
      setResp(immediate);
      setLoading(false);
    }
    if (!immediate) setLoading(true);
    const poll = () => fetchResponse(responseId)
      .then((data) => {
        if (active) {
          failures = 0;
          setResp(data);
          setLoading(false);
          if (!adminView) cacheResponse(data);
          if (responseNeedsProcessing(data)) {
            delay = Math.min(delay * 1.4, 10000);
            timer = setTimeout(poll, delay);
          }
        }
      })
      .catch(() => {
        if (active) {
          setLoading(false);
          delay = Math.min(delay * 2, 30000);
          if (++failures < 6) timer = setTimeout(poll, delay);
          else setPollError(true);
        }
      });
    void poll();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [adminView, fetchResponse, navigatedResponse, openedFromHistory, openedFromSubmission, responseId, pollAttempt]);

  if (loading) {
    if (openedFromHistory) {
      return <ResultThinkingPanel loadingInitial showAnimation />;
    }
    return (
      <div className="container max-w-xl py-24 text-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-muted-foreground">Đang tải kết quả…</p>
        </div>
      </div>
    );
  }

  if (!resp) {
    if (openedFromHistory && pollError) {
      return (
        <ResultThinkingPanel
          pollError
          showAnimation
          onRetry={() => setPollAttempt((value) => value + 1)}
        />
      );
    }
    return (
      <div className="container max-w-xl py-24 text-center">
        <p className="font-serif text-2xl">Không tìm thấy kết quả.</p>
        <p className="mt-2 text-muted-foreground">
          Phiên có thể đã hết. Hãy quay lại trang chủ và làm lại bài khảo sát.
        </p>
        <Button asChild className="mt-6">
          <Link to="/">Về trang chủ</Link>
        </Button>
      </div>
    );
  }

  const { item, mapping, scoring } = resp;
  const processing = responseNeedsProcessing(resp);
  if (resp.processing_state === "FAILED") {
    return (
      <div className="container max-w-xl py-20 text-center" role="status">
        <h1 className="font-serif text-3xl">Bài đã được lưu, xử lý đang gián đoạn</h1>
        <p className="mt-4 text-muted-foreground">Hệ thống chưa hoàn tất phân tích. Quản trị viên cần kiểm tra để xử lý lại; bạn không cần nộp lại bài.</p>
        <Button className="mt-6" onClick={() => setPollAttempt((value) => value + 1)}>Kiểm tra lại trạng thái</Button>
      </div>
    );
  }
  if (processing || resp.resolution_pending || resp.scores_stale) {
    return (
      <ResultThinkingPanel
        pollError={pollError}
        showAnimation={openedFromHistory}
        onRetry={() => setPollAttempt((value) => value + 1)}
      />
    );
  }
  const validCount = mapping.ideas.filter((i) => i.status === "VALID").length;
  const totalIdeas = mapping.ideas.length;
  if (!scoring) {
    return (
      <div className="animate-fade-in">
        <section className="border-b border-border/80 bg-muted/30">
          <div className="container max-w-4xl py-16 md:py-24">
            <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Dữ liệu đã được ghi nhận · {item.name}
            </p>
            <h1 className="mt-4 max-w-3xl font-serif text-4xl font-medium tracking-tight md:text-6xl">
              {processing ? "Bài đã được lưu và đang chấm." : "Câu trả lời của bạn đã được đóng góp vào bộ dữ liệu."}
            </h1>
            <p
              aria-live="polite"
              className="mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground"
            >
              {resp.status_message}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Badge
                variant={
                  resp.scoring_status === "PENDING_REVIEW"
                    ? "warning"
                    : "secondary"
                }
              >
                {processing
                  ? "Đang xử lý"
                  : resp.scoring_status === "PENDING_REVIEW"
                  ? (resp.resolution_pending ? "AI đang đối chiếu lại" : "Chưa đủ căn cứ phân loại")
                  : "Giai đoạn thu thập"}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {validCount}/{totalIdeas} ý đã được nhận diện
              </span>
              {resp.scoring_status === "PENDING_REVIEW" && !processing && (
                <span className="text-xs text-muted-foreground">
                  Tải lại trang hoặc mở lại từ lịch sử để xem quyết định mới.
                </span>
              )}
            </div>
          </div>
        </section>
        <section>
          <div className="container max-w-4xl py-12">
            <div className="border-l-2 border-foreground/20 pl-6">
              <p className="font-serif text-2xl">Câu trả lời đã được lưu</p>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                Bạn có thể đóng trang và mở lại kết quả này từ lịch sử khảo sát.
              </p>
            </div>
            <div className="mt-10 flex flex-wrap gap-3">
              <Button asChild>
                <Link to={`/test/${item.id}`}>
                  <RotateCcw className="h-4 w-4" /> Thử thêm một lượt
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/">
                  Chọn đồ vật khác <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </section>
      </div>
    );
  }
  const avgOriginality =
    validCount > 0 ? (scoring.originality / validCount).toFixed(2) : "0.00";
  const avgElaboration =
    validCount > 0 ? (scoring.elaboration / validCount).toFixed(2) : "0.00";

  return (
    <div className="animate-fade-in">
      {/* Header strip */}
      <section className="border-b border-border/80 bg-muted/30">
        <div className="container py-14 md:py-20">
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            Kết quả bài khảo sát
          </p>
          <div className="mt-3 flex flex-wrap items-end justify-between gap-6">
            <h1 className="font-serif text-4xl font-medium tracking-tight md:text-5xl">
              {item.name} <span className="text-muted-foreground">·</span>{" "}
              <span className="text-muted-foreground">đánh giá hoàn tất</span>
            </h1>
          </div>
          <p className="mt-4 max-w-2xl text-muted-foreground">
            Bạn đã nghĩ ra{" "}
            <strong className="text-foreground">{totalIdeas}</strong> ý tưởng,
            trong đó <strong className="text-foreground">{validCount}</strong> ý
            hợp lệ. Dưới đây là chi tiết đánh giá về ý tưởng của bạn.
          </p>
        </div>
      </section>

      {/* Metrics */}
      <section className="border-b border-border/80">
        <div className="container py-12">
          <div className="grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Số lượng ý"
              vi="Số ý tưởng hợp lệ"
              value={scoring.fluency}
              accent
            />
            <Metric
              label="Độ linh hoạt"
              vi="Số nhóm công dụng khác nhau"
              value={scoring.flexibility}
            />
            <Metric
              label="Độ độc đáo"
              vi={`Mức độ mới lạ của ý tưởng · Trung bình ${avgOriginality}/2`}
              value={scoring.originality}
            />
            <Metric
              label="Độ chi tiết"
              vi={`Mức độ rõ ràng của mô tả · Trung bình ${avgElaboration}/5`}
              value={scoring.elaboration}
            />
          </div>
        </div>
      </section>

      {/* Summary */}
      {scoring.summary_vi && (
        <section className="border-b border-border/80 bg-muted/30">
          <div className="container py-12">
            <div className="grid gap-10 md:grid-cols-[1fr_2fr]">
              <div>
                <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                  Nhận xét tổng thể
                </p>
                <h2 className="mt-3 font-serif text-2xl">
                  Hướng sáng tạo trong bài của bạn
                </h2>
              </div>
              <div className="border-l-2 border-foreground/40 pl-6">
                <p className="whitespace-pre-line text-base leading-7 text-foreground/90">{scoring.summary_vi}</p>
                <p className="mt-4 text-xs leading-5 text-muted-foreground">Nhận xét chỉ phản ánh các ý được phân tích trong bài này, không kết luận về tính cách hay năng lực sáng tạo cố định của bạn.</p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Mapping table */}
      <section className="border-b border-border/80">
        <div className="container py-12">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                Cách hệ thống hiểu câu trả lời
              </p>
              <h2 className="mt-3 font-serif text-2xl">
                Chi tiết ý tưởng của bạn
              </h2>
            </div>
          </div>

          <ul className="mt-8 grid gap-3 md:hidden">
            {mapping.ideas.map((idea, idx) => {
              const dimmed = idea.status !== "VALID";
              return (
                <li
                  key={`${idea.line_index}-${idx}`}
                  className={cn(
                    "rounded-xl border border-border bg-card p-4",
                    dimmed && "bg-muted/20 text-muted-foreground",
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-xs text-muted-foreground">
                      Ý tưởng {(idx + 1).toString().padStart(2, "0")}
                    </span>
                    <Badge variant={STATUS_VARIANT[idea.status]}>
                      {STATUS_LABEL[idea.status]}
                    </Badge>
                  </div>
                  <p className="mt-3 break-words text-sm leading-6">
                    {idea.original || <span className="italic">(trống)</span>}
                  </p>
                  {idea.normalized && idea.normalized !== idea.original ? (
                    <p className="mt-3 border-l-2 border-border pl-3 text-xs leading-5 text-muted-foreground">
                      Hệ thống hiểu: {idea.normalized}
                    </p>
                  ) : null}
                  {idea.reason ? (
                    <p className="mt-2 text-xs italic leading-5 text-muted-foreground">
                      {idea.reason}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>

          <TableViewport className="mt-8 hidden md:block">
            <Table className="min-w-[820px]">
              <caption className="sr-only">
                Cách hệ thống hiểu và phân loại từng ý tưởng của bạn
              </caption>
              <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-[0.14em] text-muted-foreground">
                <tr>
                  <th className="w-12 px-4 py-3 font-medium">#</th>
                  <th className="px-4 py-3 font-medium">Câu gốc</th>
                  <th className="px-4 py-3 font-medium">Diễn giải</th>
                  <th className="px-4 py-3 font-medium">Nhóm ý tưởng</th>
                  <th className="px-4 py-3 font-medium">Trạng thái</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border bg-card">
                {mapping.ideas.map((idea, idx) => {
                  const dimmed = idea.status !== "VALID";
                  return (
                    <tr
                      key={idx}
                      className={cn(
                        dimmed && "bg-muted/20 text-muted-foreground",
                      )}
                    >
                      <td className="px-4 py-4 align-top font-mono text-xs text-muted-foreground">
                        {(idx + 1).toString().padStart(2, "0")}
                      </td>
                      <td className="px-4 py-4 align-top leading-relaxed">
                        {idea.original || (
                          <span className="italic">(trống)</span>
                        )}
                      </td>
                      <td className="px-4 py-4 align-top leading-relaxed">
                        {idea.normalized}
                        {idea.reason && (
                          <p className="mt-1 text-xs italic text-muted-foreground">
                            {idea.reason}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-4 align-top">
                        <span className="font-mono text-xs">{idea.code}</span>
                      </td>
                      <td className="px-4 py-4 align-top">
                        <Badge variant={STATUS_VARIANT[idea.status]}>
                          {STATUS_LABEL[idea.status]}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </TableViewport>
        </div>
      </section>

      {/* Per idea scoring */}
      <PerIdeaSection resp={resp} />

      {/* Footer CTA */}
      <section className="bg-muted/30">
        <div className="container flex flex-col items-center gap-5 py-16 text-center">
          <h2 className="font-serif text-3xl">Thử với một đồ vật khác?</h2>
          <p className="max-w-md text-muted-foreground">
            Mỗi đồ vật gợi ra những hướng liên tưởng khác nhau. Thử thêm một đồ
            vật để khám phá cách bạn chuyển đổi góc nhìn.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg">
              <Link to={`/test/${item.id}`}>
                <RotateCcw className="h-4 w-4" /> Làm lại với {item.name}
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link to="/">
                Đổi đồ vật <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function Metric({
  label,
  vi,
  value,
  hint,
  accent,
}: {
  label: string;
  vi: string;
  value: number;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={cn("bg-card p-7", accent && "bg-foreground text-background")}
    >
      <p
        className={cn(
          "text-[11px] uppercase tracking-[0.18em]",
          accent ? "text-background/70" : "text-muted-foreground",
        )}
      >
        {label}
      </p>
      <p className="mt-3 font-serif text-5xl tabular-nums leading-none">
        {value}
      </p>
      <p
        className={cn(
          "mt-3 text-xs",
          accent ? "text-background/70" : "text-muted-foreground",
        )}
      >
        {vi}
      </p>
      {hint && (
        <p
          className={cn(
            "mt-3 line-clamp-2 text-xs leading-relaxed",
            accent ? "text-background/70" : "text-muted-foreground",
          )}
          title={hint}
        >
          {hint}
        </p>
      )}
    </div>
  );
}

function PerIdeaSection({ resp }: { resp: ScoreResponse }) {
  const items = useMemo(() => resp.scoring?.per_idea_scores ?? [], [resp]);
  if (items.length === 0) return null;

  return (
    <section className="border-b border-border/80">
      <div className="container py-12">
        <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
          Đánh giá từng ý tưởng
        </p>
        <h2 className="mt-3 font-serif text-2xl">Điểm chi tiết từng ý</h2>

        <ul className="mt-8 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2">
          {items.map((it, idx) => (
            <li key={idx} className="bg-card p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="font-mono text-xs text-muted-foreground">
                    Ý tưởng {(idx + 1).toString().padStart(2, "0")}
                  </p>
                  <p className="mt-1 font-serif text-lg leading-snug">
                    {it.normalized}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-3">
                  <ScorePill label="Độc đáo" value={it.originality} max={2} />
                  <ScorePill label="Chi tiết" value={it.elaboration} max={5} />
                </div>
              </div>
              {it.note && (
                <p className="mt-3 text-sm italic leading-relaxed text-muted-foreground">
                  {it.note}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function ScorePill({
  label,
  value,
  max,
}: {
  label: string;
  value: number;
  max: number;
}) {
  return (
    <div className="rounded-md border border-border bg-muted/40 px-3 py-1.5 text-center">
      <p className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </p>
      <p className="font-mono text-sm font-medium tabular-nums">
        {value}
        <span className="text-muted-foreground">/{max}</span>
      </p>
    </div>
  );
}
