import { useEffect, useRef, useState } from "react";
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
    name: "Số lượng ý tưởng",
    body: "Đếm số ý tưởng hợp lệ. Càng nhiều ý tưởng phù hợp, điểm càng cao.",
  },
  {
    code: "II",
    name: "Sự đa dạng",
    body: "Đo số nhóm ý tưởng khác nhau. Các ý tưởng cùng nhóm không cộng thêm.",
  },
  {
    code: "III",
    name: "Độ độc đáo",
    body: "Đánh giá mức độ mới lạ và khác biệt của từng ý tưởng.",
  },
  {
    code: "IV",
    name: "Mức độ chi tiết",
    body: "Đánh giá độ rõ ràng, cụ thể và đầy đủ trong cách mô tả ý tưởng.",
  },
] as const;

/** true nếu trình duyệt yêu cầu giảm chuyển động — tắt hiệu ứng khi cần. */
function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
  }, []);
  return reduced;
}

/** Trả về ref + trạng thái "đã lọt vào khung nhìn" để kích hoạt hiệu ứng khi cuộn tới. */
function useRevealOnScroll<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.unobserve(el);
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, visible };
}

// Các kết quả mẫu để "Mẫu kết quả" tự luân phiên minh hoạ nhiều đồ vật khác nhau.
const SAMPLE_RESULTS = [
  {
    object: "Đũa",
    scores: [
      { label: "Số ý", value: "7" },
      { label: "Đa dạng", value: "5" },
      { label: "Độc đáo", value: "3" },
      { label: "Chi tiết", value: "16" },
    ],
    quote:
      "Ý tưởng linh hoạt ở nhóm vũ khí và nhạc cụ, nhưng có thể đẩy độ độc đáo của ý tưởng cao hơn bằng các công dụng trong nấu nướng.",
  },
  {
    object: "Ly giấy",
    scores: [
      { label: "Số ý", value: "9" },
      { label: "Đa dạng", value: "6" },
      { label: "Độc đáo", value: "5" },
      { label: "Chi tiết", value: "21" },
    ],
    quote:
      "Ý tưởng trải đều nhiều danh mục, đặc biệt mạnh ở nhóm đồ chơi và dụng cụ đo lường tự chế.",
  },
  {
    object: "Kẹp giấy",
    scores: [
      { label: "Số ý", value: "11" },
      { label: "Đa dạng", value: "4" },
      { label: "Độc đáo", value: "6" },
      { label: "Chi tiết", value: "12" },
    ],
    quote:
      "Nhiều ý táo bạo nhưng tập trung quanh nhóm công cụ nhỏ, thử mở rộng sang nghệ thuật hoặc trang sức.",
  },
] as const;

/** Thời gian (ms) hiển thị mỗi kết quả mẫu trước khi chuyển sang cái tiếp theo. */
const SAMPLE_INTERVAL_MS = 2500;
/** Thời gian (ms) của hiệu ứng mờ dần giữa hai kết quả. */
const SAMPLE_FADE_MS = 350;

export default function Home() {
  const location = useLocation();
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sampleIndex, setSampleIndex] = useState(0);
  const [sampleVisible, setSampleVisible] = useState(true);

  useEffect(() => {
    let fadeTimeout: ReturnType<typeof setTimeout>;
    const interval = setInterval(() => {
      setSampleVisible(false);
      fadeTimeout = setTimeout(() => {
        setSampleIndex((i) => (i + 1) % SAMPLE_RESULTS.length);
        setSampleVisible(true);
      }, SAMPLE_FADE_MS);
    }, SAMPLE_INTERVAL_MS);
    return () => {
      clearInterval(interval);
      clearTimeout(fadeTimeout);
    };
  }, []);

  const sample = SAMPLE_RESULTS[sampleIndex];
  const reducedMotion = usePrefersReducedMotion();
  const [heroLoaded, setHeroLoaded] = useState(false);
  const methodReveal = useRevealOnScroll<HTMLDivElement>();
  const itemsReveal = useRevealOnScroll<HTMLDivElement>();

  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => setHeroLoaded(true));
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  /** Style fade + trượt lên dùng chung cho mọi hiệu ứng reveal. */
  const reveal = (visible: boolean, delayMs = 0) =>
    reducedMotion
      ? undefined
      : ({
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0px)" : "translateY(16px)",
          transition: `opacity 500ms ease ${delayMs}ms, transform 500ms ease ${delayMs}ms`,
        } as const);

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
          <div style={reveal(heroLoaded)}>
            <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5" />
              Đo tư duy phân kỳ ·
            </p>
            <h1 className="font-serif text-4xl font-medium leading-[1.05] tracking-tight text-balance md:text-6xl">
              Cách bạn dùng một đồ vật bình thường có thể tiết lộ
              <span className="text-muted-foreground"> cách bạn tư duy.</span>
            </h1>
            <p className="mt-6 max-w-xl text-pretty text-base leading-relaxed text-muted-foreground md:text-lg">
              {" "}
              <span className="font-medium text-foreground">
                Bài kiểm tra công dụng thay thế (AUT)
              </span>{" "}
              là bài kiểm tra tư duy sáng tạo của Guilford. Từ những đồ vật quen
              thuộc, hãy thử nghĩ ra những cách sử dụng khác biệt nhất. Mỗi câu
              trả lời sẽ được phân tích và đánh giá qua 4 khía cạnh của tư duy
              sáng tạo — từ khả năng tạo ra nhiều ý tưởng đến mức độ độc đáo và
              chi tiết.
            </p>

            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Button asChild size="lg">
                <a href="#chon-do-vat">
                  Bắt đầu khảo sát <ArrowRight className="h-4 w-4" />
                </a>
              </Button>
              <Button asChild variant="ghost" size="lg">
                <a href="#phuong-phap">Xem phương pháp chấm</a>
              </Button>
            </div>
          </div>

          {/* Paper card */}
          <div className="md:pl-6" style={reveal(heroLoaded, 150)}>
            <Card className="relative bg-card shadow-[0_1px_0_hsl(var(--border)),0_24px_48px_-32px_rgba(0,0,0,0.18)]">
              <div className="absolute -top-3 left-6 rounded-sm bg-foreground px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.2em] text-background">
                Mẫu kết quả
              </div>
              <CardContent className="space-y-5 p-7 pt-8">
                <div
                  style={{
                    opacity: sampleVisible ? 1 : 0,
                    transform: sampleVisible
                      ? "translateY(0px)"
                      : "translateY(4px)",
                    transition: `opacity ${SAMPLE_FADE_MS}ms ease, transform ${SAMPLE_FADE_MS}ms ease`,
                  }}
                  className="space-y-5"
                >
                  <div className="space-y-1">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                      Đồ vật
                    </p>
                    <p className="font-serif text-2xl">{sample.object}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
                    {sample.scores.map(({ label, value }) => (
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
                    “{sample.quote}”
                  </p>
                </div>
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
              BỐN KHÍA CẠNH CỦA TƯ DUY SÁNG TẠO
            </p>
            <h2 className="mt-3 font-serif text-3xl font-medium tracking-tight md:text-4xl">
              Một bài khảo sát, bốn lăng kính.
            </h2>
            <p className="mt-4 text-pretty text-muted-foreground">
              Mỗi câu trả lời được phân tích qua bốn khía cạnh khác nhau, từ số
              lượng ý tưởng đến mức độ đa dạng, độc đáo và chi tiết — giúp phác
              họa rõ hơn cách bạn tư duy sáng tạo.
            </p>
          </div>

          <div
            ref={methodReveal.ref}
            className="mt-14 grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2 lg:grid-cols-4"
          >
            {DIMENSIONS.map((d, i) => (
              <article
                key={d.code}
                className="bg-card p-7"
                style={reveal(methodReveal.visible, i * 70)}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">
                    {d.code}
                  </span>
                  <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    Tiêu chí {d.code}
                  </span>
                </div>
                <h3 className="mt-6 font-serif text-2xl text-center">
                  {d.name}
                </h3>
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

          <div className="mt-12 " ref={itemsReveal.ref}>
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
                  <li
                    key={item.id}
                    className="bg-card"
                    style={reveal(itemsReveal.visible, Math.min(idx, 6) * 70)}
                  >
                    <Link
                      to={`/test/${item.id}`}
                      className="group flex h-full flex-col gap-4 p-7 transition-colors hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none"
                    >
                      <div className="flex items-start justify-between">
                        <span className="font-mono text-xs text-muted-foreground">
                          {(idx + 1).toString().padStart(2, "0")}
                        </span>
                        <span className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                          Sổ mã động
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
