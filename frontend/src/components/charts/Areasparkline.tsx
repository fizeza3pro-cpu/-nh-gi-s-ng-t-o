import { useEffect, useState } from "react";

interface AreaSparklineProps {
  values: number[];
  labels: string[];
  color?: string;
  height?: number;
  /** Thời gian (ms) để vẽ xong toàn bộ đường + vùng tô, mặc định 900ms */
  animationDuration?: number;
}

/** Biểu đồ đường + vùng tô mờ bên dưới, tự vẽ bằng SVG, có hiệu ứng vẽ dần khi mount. */
export function AreaSparkline({
  values,
  labels,
  color = "#2E5CE6",
  height = 140,
  animationDuration = 900,
}: AreaSparklineProps) {
  const width = 600;
  const padTop = 14;
  const padBottom = 28;
  const chartH = height - padTop - padBottom;
  const max = Math.max(...values, 1);
  const min = 0;
  const step = values.length > 1 ? width / (values.length - 1) : 0;

  const [animate, setAnimate] = useState(false);
  const fingerprint = values.join(",");

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

  const points = values.map((v, i) => {
    const x = i * step;
    const y = padTop + chartH - ((v - min) / (max - min || 1)) * chartH;
    return [x, y] as const;
  });

  function smoothPath(pts: readonly (readonly [number, number])[]): string {
    if (pts.length < 2) return "";
    let d = `M ${pts[0][0]},${pts[0][1]}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const [x0, y0] = pts[i];
      const [x1, y1] = pts[i + 1];
      const midX = (x0 + x1) / 2;
      d += ` Q ${x0},${y0} ${midX},${(y0 + y1) / 2}`;
    }
    const last = pts[pts.length - 1];
    d += ` T ${last[0]},${last[1]}`;
    return d;
  }

  const linePath = smoothPath(points);
  const areaPath = `${linePath} L ${width},${padTop + chartH} L 0,${padTop + chartH} Z`;

  const gradId = `spark-grad-${color.replace("#", "")}`;
  const showLabels = labels.filter(
    (_, i) => i % Math.ceil(labels.length / 6) === 0,
  );

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      preserveAspectRatio="none"
      style={{ height }}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d={areaPath}
        fill={`url(#${gradId})`}
        style={{
          clipPath: animate ? "inset(0 0% 0 0)" : "inset(0 100% 0 0)",
          transition: `clip-path ${animationDuration}ms ease-out`,
        }}
      />
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth="2.5"
        strokeLinecap="round"
        pathLength={1}
        style={{
          strokeDasharray: 1,
          strokeDashoffset: animate ? 0 : 1,
          transition: `stroke-dashoffset ${animationDuration}ms ease-out`,
        }}
      />
      {points.length > 0 && (
        <circle
          cx={points[points.length - 1][0]}
          cy={points[points.length - 1][1]}
          r="4"
          fill={color}
          style={{
            opacity: animate ? 1 : 0,
            transition: `opacity 200ms ease-out ${animationDuration - 150}ms`,
          }}
        />
      )}
      <g className="fill-muted-foreground" style={{ fontSize: 11 }}>
        {showLabels.map((l, i) => {
          const idx = labels.indexOf(l);
          const x = idx * step;
          return (
            <text
              key={l}
              x={i === 0 ? x : x}
              y={height - 8}
              textAnchor={
                idx === 0
                  ? "start"
                  : idx === labels.length - 1
                    ? "end"
                    : "middle"
              }
            >
              {l}
            </text>
          );
        })}
      </g>
    </svg>
  );
}
