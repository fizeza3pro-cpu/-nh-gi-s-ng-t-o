import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Sparkles, Timer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Item } from "@/lib/types";

const DIMENSIONS = [
  {
    code: "I",
    name: "Fluency",
    vi: "Số lượng ý",
    body: "Đếm số ý tưởng hợp lệ. Càng nhiều ý khả thi, càng cao.",
  },
  {
    code: "II",
    name: "Flexibility",
    vi: "Số danh mục khác nhau",
    body: "Đếm số nhóm khái niệm. Lặp lại cùng nhóm không cộng thêm.",
  },
  {
    code: "III",
    name: "Originality",
    vi: "Độ hiếm và bất ngờ",
    body: "Mỗi ý chấm 0–2 dựa trên uncommonness · remoteness · cleverness.",
  },
  {
    code: "IV",
    name: "Elaboration",
    vi: "Mức độ chi tiết",
    body: "Mỗi ý chấm 1–5 theo độ rõ ràng, ngữ cảnh và mô tả cụ thể.",
  },
] as const;

export default function Home() {
  const location = useLocation();
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hash = location.hash;
    if (hash) {
      const elementId = hash.replace("#", "");
      const element = document.getElementById(elementId);

      if (element) {
        setTimeout(() => {
          element.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }, 300);
      }
    }
  }, [location]);

  useEffect(() => {
    api
      .listItems()
      .then(setItems)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="animate-fade-in">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border/80">
        <div className="absolute inset-0 grid-paper opacity-40" aria-hidden />
        <div className="container relative grid gap-12 py-20 md:grid-cols-[1.4fr_1fr] md:py-28">
          <div>
            <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5" />
              Đo tư duy phân kỳ · LLM-as-a-Judge
            </p>
            <h1 className="font-serif text-4xl font-medium leading-[1.05] tracking-tight text-balance md:text-6xl">
              Cách bạn dùng một đồ vật bình thường có thể tiết lộ
              <span className="text-muted-foreground"> cách bạn tư duy.</span>
            </h1>
            <p className="mt-6 max-w-xl text-pretty text-base leading-relaxed text-muted-foreground md:text-lg">
              Alternative Uses Test (AUT) là bài kiểm tra kinh điển của Guilford
              đo khả năng sáng tạo. Phiên bản tiếng Việt này dùng pipeline 2
              tầng{" "}
              <span className="font-medium text-foreground">
                Mapping → Scoring
              </span>{" "}
              để hiểu ý định người dùng trước khi chấm — kể cả khi câu trả lời
              tự do, lộn xộn, không cấu trúc.
            </p>

            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Button asChild size="lg">
                <a href="#chon-do-vat">
                  Bắt đầu test <ArrowRight className="h-4 w-4" />
                </a>
              </Button>
              <Button asChild variant="ghost" size="lg">
                <a href="#phuong-phap">Xem phương pháp chấm</a>
              </Button>
            </div>
          </div>

          {/* Paper card */}
          <div className="md:pl-6">
            <Card className="relative bg-card shadow-[0_1px_0_hsl(var(--border)),0_24px_48px_-32px_rgba(0,0,0,0.18)]">
              <div className="absolute -top-3 left-6 rounded-sm bg-foreground px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.2em] text-background">
                Mẫu kết quả
              </div>
              <CardContent className="space-y-5 p-7 pt-8">
                <div className="space-y-1">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                    Đồ vật
                  </p>
                  <p className="font-serif text-2xl">Đũa</p>
                </div>
                <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
                  {[
                    ["Fluency", "7"],
                    ["Flexibility", "5"],
                    ["Originality", "3"],
                    ["Elaboration", "16"],
                  ].map(([label, value]) => (
                    <div key={label} className="bg-card p-4">
                      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                        {label}
                      </p>
                      <p className="mt-1 font-serif text-3xl tabular-nums">
                        {value}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="border-l-2 border-foreground/60 pl-4 text-sm italic leading-relaxed text-muted-foreground">
                  “Bạn linh hoạt ở nhóm vũ khí và nhạc cụ, nhưng có thể đẩy
                  Originality cao hơn bằng các công dụng phi-bếp.”
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Phương pháp */}
      <section
        id="phuong-phap"
        className="border-b border-border/80 bg-muted/30"
      >
        <div className="container py-20">
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Bốn chiều đo của Guilford
            </p>
            <h2 className="mt-3 font-serif text-3xl font-medium tracking-tight md:text-4xl">
              Một bài test, bốn lăng kính.
            </h2>
            <p className="mt-4 text-pretty text-muted-foreground">
              Pipeline tách bước hiểu nghĩa khỏi bước chấm điểm, để mỗi chiều
              được đo trên ý tưởng đã chuẩn hoá — không bị nhiễu bởi cách diễn
              đạt.
            </p>
          </div>

          <div className="mt-14 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-4">
            {DIMENSIONS.map((d) => (
              <article key={d.code} className="bg-card p-7">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">
                    {d.code}
                  </span>
                  <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    {d.vi}
                  </span>
                </div>
                <h3 className="mt-6 font-serif text-2xl">{d.name}</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {d.body}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Chọn đồ vật */}
      <section id="chon-do-vat" className="border-b border-border/80">
        <div className="container py-20">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div className="max-w-xl">
              <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                Chọn một đồ vật bản địa
              </p>
              <h2 className="mt-3 font-serif text-3xl font-medium tracking-tight md:text-4xl">
                Bạn có 3 phút. Liệt kê càng nhiều cách dùng càng tốt.
              </h2>
            </div>
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Timer className="h-4 w-4" />
              Mỗi bài kéo dài 180 giây.
            </p>
          </div>

          <div className="mt-12">
            {error && (
              <p className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
                {error}
              </p>
            )}

            {!items && !error && (
              <div className="grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="space-y-3 bg-card p-7">
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="h-7 w-2/3" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                ))}
              </div>
            )}

            {items && (
              <ul className="grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-3">
                {items.map((item, idx) => (
                  <li key={item.id} className="bg-card">
                    <Link
                      to={`/test/${item.id}`}
                      className="group flex h-full flex-col gap-4 p-7 transition-colors hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none"
                    >
                      <div className="flex items-start justify-between">
                        <span className="font-mono text-xs text-muted-foreground">
                          {(idx + 1).toString().padStart(2, "0")}
                        </span>
                        <span className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                          {item.codes.length} danh mục
                        </span>
                      </div>
                      <h3 className="font-serif text-3xl">{item.name}</h3>
                      <p className="text-sm leading-relaxed text-muted-foreground">
                        {item.description}
                      </p>
                      <span className="mt-auto inline-flex items-center gap-2 text-sm font-medium text-foreground/80 transition-colors group-hover:text-foreground">
                        Chọn đồ vật này
                        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
