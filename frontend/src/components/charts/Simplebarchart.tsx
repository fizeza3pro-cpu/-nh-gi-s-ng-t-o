interface BarChartProps {
  data: { label: string; value: number }[];
  color?: string;
  height?: number;
}

/** Biểu đồ cột dọc, tự vẽ bằng SVG. Cột cao nhất được tô đậm hơn để làm nổi bật. */
export function SimpleBarChart({
  data,
  color = "#2E5CE6",
  height = 220,
}: BarChartProps) {
  const width = 600;
  const padBottom = 28;
  const padTop = 10;
  const chartH = height - padBottom - padTop;
  const max = Math.max(...data.map((d) => d.value), 1);
  const gap = 14;
  const barW = (width - gap * (data.length - 1)) / data.length;
  const maxIndex = data.reduce(
    (best, d, i) => (d.value > data[best].value ? i : best),
    0,
  );

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      preserveAspectRatio="none"
      style={{ height }}
    >
      {data.map((d, i) => {
        const barH = (d.value / max) * chartH;
        const x = i * (barW + gap);
        const y = padTop + chartH - barH;
        return (
          <g key={d.label}>
            <rect
              x={x}
              y={y}
              width={barW}
              height={barH}
              rx={6}
              fill={i === maxIndex ? color : `${color}55`}
            />
            <text
              x={x + barW / 2}
              y={height - 8}
              textAnchor="middle"
              className="fill-slate-400"
              style={{ fontSize: 11 }}
            >
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
