import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ArrowRight, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, readCachedResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { IdeaStatus, ScoreResponse } from "@/lib/types";

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
  const navigatedResponse = (
    location.state as { response?: ScoreResponse } | null
  )?.response;
  const initialResponse = navigatedResponse ?? (
    responseId ? readCachedResponse(responseId) : null
  );
  const [resp, setResp] = useState<ScoreResponse | null>(initialResponse);
  const [loading, setLoading] = useState(!initialResponse);

  useEffect(() => {
    if (!responseId) {
      setLoading(false);
      return;
    }

    const immediate = navigatedResponse ?? readCachedResponse(responseId);
    if (immediate) {
      setResp(immediate);
      setLoading(false);
      return;
    }
    setLoading(true);
    // Cache miss (mở từ lịch sử hoặc reload) → lấy từ backend.
    api
      .getResponse(responseId)
      .then((data) => {
        setResp(data);
        setLoading(false);
      })
      .catch(() => {
        setResp(null);
        setLoading(false);
      });
  }, [navigatedResponse, responseId]);

  if (loading) {
    return (
      <div className="container max-w-xl py-24 text-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-muted-foreground">Đang tải kết quả...</p>
        </div>
      </div>
    );
  }

  if (!resp) {
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
              Câu trả lời của bạn đang giúp hình thành chuẩn đánh giá.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground">
              {resp.status_message}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Badge variant={resp.scoring_status === "PENDING_REVIEW" ? "warning" : "secondary"}>
                {resp.scoring_status === "PENDING_REVIEW" ? "AI đang đối chiếu lại" : "Giai đoạn thu thập"}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {validCount}/{totalIdeas} ý đã được nhận diện
              </span>
            </div>
          </div>
        </section>
        <section>
          <div className="container max-w-4xl py-12">
            <div className="border-l-2 border-foreground/20 pl-6">
              <p className="font-serif text-2xl">Không có ý nào bị tính điểm 0 vì thiếu dữ liệu.</p>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                Khi đồ vật đạt ngưỡng hiệu chuẩn, hệ thống sẽ tự đóng phiên bản sổ mã và chấm bù
                mọi lượt đã gửi. Kết quả vẫn được lưu để truy xuất sau.
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
              vi="Danh mục bạn đã nghĩ ra"
              value={scoring.flexibility}
            />
            <Metric
              label="Độ độc đáo"
              vi={`Điểm độc đáo về các ý tưởng của bạn Trung bình ${avgOriginality} / 2`}
              value={scoring.originality}
            />
            <Metric
              label="Độ chi tiết"
              vi={`Điểm số thể hiện độ mạch lạc của ý tưởng; Trung bình ${avgElaboration} / 5`}
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
                  Bạn tư duy thế nào?
                </h2>
              </div>
              <blockquote className="border-l-2 border-foreground/40 pl-6 font-serif text-xl leading-relaxed text-foreground/90">
                “{scoring.summary_vi}”
              </blockquote>
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
                Tầng 1 · Chuẩn hoá ngữ nghĩa
              </p>
              <h2 className="mt-3 font-serif text-2xl">
                Chi tiết ý tưởng của bạn
              </h2>
            </div>
          </div>

          <div className="mt-8 overflow-hidden rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-[0.14em] text-muted-foreground">
                <tr>
                  <th className="w-12 px-4 py-3 font-medium">#</th>
                  <th className="px-4 py-3 font-medium">Câu gốc</th>
                  <th className="px-4 py-3 font-medium">Diễn giải</th>
                  <th className="px-4 py-3 font-medium">Mã</th>
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
            </table>
          </div>
        </div>
      </section>

      {/* Per idea scoring */}
      <PerIdeaSection resp={resp} />

      {/* Footer CTA */}
      <section className="bg-muted/30">
        <div className="container flex flex-col items-center gap-5 py-16 text-center">
          <h2 className="font-serif text-3xl">Thử với một đồ vật khác?</h2>
          <p className="max-w-md text-muted-foreground">
            Mỗi đồ vật mở ra một bộ danh mục khác. Điểm linh hoạt chỉ thật sự
            nói lên điều gì khi bạn thử qua nhiều đồ vật.
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
          Tầng 2 · Chấm điểm
        </p>
        <h2 className="mt-3 font-serif text-2xl">Điểm chi tiết từng ý</h2>

        <ul className="mt-8 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2">
          {items.map((it, idx) => (
            <li key={idx} className="bg-card p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-mono text-xs text-muted-foreground">
                    {(idx + 1).toString().padStart(2, "0")} · {it.code}
                  </p>
                  <p className="mt-1 font-serif text-lg leading-snug">
                    {it.normalized}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
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
