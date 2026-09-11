import { useEffect, useState } from "react";

interface DonutChartProps {
  data: { label: string; value: number; color: string }[];
  total: number;
  totalLabel?: string;
  size?: number;
  /** Thời gian (ms) để "vẽ" hết cả vòng tròn, mặc định 900ms */
  animationDuration?: number;
}

/** Biểu đồ donut (vành khuyên) + tổng số ở tâm, tự vẽ bằng SVG, có hiệu ứng mở ra khi mount. */
export function DonutChart({
  data,
  total,
  totalLabel = "Tổng",
  size = 180,
  animationDuration = 500,
}: DonutChartProps) {
  const r = size / 2;
  const strokeWidth = size * 0.22;
  const innerR = r - strokeWidth / 2;
  const circumference = 2 * Math.PI * innerR;
  const sum = data.reduce((s, d) => s + d.value, 0) || 1;

  const [animate, setAnimate] = useState(false);
  // "chữ ký" dữ liệu để phát lại animation mỗi khi data đổi (vd. filter)
  const fingerprint = data.map((d) => `${d.label}:${d.value}`).join("|");

  useEffect(() => {
    setAnimate(false);
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setAnimate(true));
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, [fingerprint]);

  let offsetAcc = 0;
  const segments = data.map((d) => {
    const frac = d.value / sum;
    const dash = frac * circumference;
    const startOffset = offsetAcc;
    const seg = {
      ...d,
      dash,
      dashOffset: -startOffset,
      pct: Math.round(frac * 100),
      delay: (startOffset / circumference) * animationDuration,
      duration: Math.max((dash / circumference) * animationDuration, 120),
    };
    offsetAcc += dash;
    return seg;
  });

  return (
    <div className="flex items-center gap-8">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <g transform={`rotate(-90 ${r} ${r})`}>
            {segments.map((s) => (
              <circle
                key={s.label}
                cx={r}
                cy={r}
                r={innerR}
                fill="none"
                stroke={s.color}
                strokeWidth={strokeWidth}
                strokeDasharray={
                  animate
                    ? `${s.dash} ${circumference - s.dash}`
                    : `0 ${circumference}`
                }
                strokeDashoffset={s.dashOffset}
                style={{
                  transition: `stroke-dasharray ${s.duration}ms ease-out ${s.delay}ms`,
                }}
              />
            ))}
          </g>
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <p className="text-[11px] text-muted-foreground">{totalLabel}</p>
          <p className="text-xl font-bold tabular-nums">
            {total.toLocaleString("vi-VN")}
          </p>
        </div>
      </div>
      <ul className="space-y-2.5">
        {segments.map((s) => (
          <li key={s.label} className="flex items-center gap-2.5 text-sm">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="text-foreground/80">{s.label}</span>
            <span className="ml-auto pl-4 text-muted-foreground">
              {s.value.toLocaleString("vi-VN")} ({s.pct}%)
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
