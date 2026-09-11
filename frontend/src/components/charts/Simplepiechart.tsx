interface PieChartProps {
  data: { label: string; value: number; color: string }[];
  size?: number;
}

/** Biểu đồ tròn tự vẽ bằng SVG (dùng path arc thủ công, không cần thư viện). */
export function SimplePieChart({ data, size = 220 }: PieChartProps) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const r = size / 2;
  const cx = r;
  const cy = r;

  let angleStart = -90; // bắt đầu từ đỉnh 12 giờ

  function polar(angleDeg: number): [number, number] {
    const rad = (angleDeg * Math.PI) / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
  }

  const slices = data.map((d) => {
    const angleSize = (d.value / total) * 360;
    const angleEnd = angleStart + angleSize;
    const [x0, y0] = polar(angleStart);
    const [x1, y1] = polar(angleEnd);
    const largeArc = angleSize > 180 ? 1 : 0;
    const path = `M ${cx},${cy} L ${x0},${y0} A ${r},${r} 0 ${largeArc} 1 ${x1},${y1} Z`;
    const midAngle = angleStart + angleSize / 2;
    const [lx, ly] = polar(midAngle * (angleSize > 28 ? 0.62 : 1.22));
    angleStart = angleEnd;
    return {
      ...d,
      path,
      pct: Math.round((d.value / total) * 100),
      lx,
      ly,
      showInside: angleSize > 28,
    };
  });

  return (
    <div className="flex items-center gap-8">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {slices.map((s) => (
          <path
            key={s.label}
            d={s.path}
            fill={s.color}
            stroke="white"
            strokeWidth={2}
          />
        ))}
        {slices.map((s) => (
          <text
            key={`${s.label}-label`}
            x={s.lx}
            y={s.ly}
            textAnchor="middle"
            dominantBaseline="middle"
            className={s.showInside ? "fill-white" : "fill-slate-500"}
            style={{ fontSize: 13, fontWeight: 600 }}
          >
            {s.pct}%
          </text>
        ))}
      </svg>
      <ul className="space-y-3">
        {data.map((d) => (
          <li
            key={d.label}
            className="flex items-center gap-2.5 text-sm text-slate-600"
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: d.color }}
            />
            {d.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
