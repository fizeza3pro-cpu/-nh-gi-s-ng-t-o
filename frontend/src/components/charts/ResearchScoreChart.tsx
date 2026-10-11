import { useId, type RefObject } from "react";
import type { AdminResearchReport } from "@/lib/report-types";
import { DIMENSION_LABELS, GROUP_COLORS, GROUP_LABELS, pText, reportItemsText, scoreText } from "@/lib/research-report";

export function ResearchScoreChart({ report, svgRef }: {
  report: AdminResearchReport;
  svgRef: RefObject<SVGSVGElement>;
}) {
  const id = useId();
  const { dimensions } = report;
  const width = 1000;
  const left = 70;
  const right = 30;
  const top = 130;
  const bottom = 430;
  const step = (width - left - right) / 4;
  const maximum = Math.max(1, ...dimensions.flatMap(row => [row.low, row.high].map(score => (score.mean ?? 0) + (score.sem ?? 0))));
  const ceiling = Math.max(4, Math.ceil(maximum * 1.18 / 4) * 4);
  const y = (value: number) => bottom - (value / ceiling) * (bottom - top);
  const context = `${report.data_source} · ${reportItemsText(report, true)}`;
  return (
    <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 630"
      width="1000" height="630" className="h-auto w-full min-w-[740px]"
      role="img" aria-labelledby={`${id}-title ${id}-description`}
      style={{ background: "white", color: "#1c1917", fontFamily: "Arial, sans-serif" }}>
      <title id={`${id}-title`}>Điểm trung bình theo bốn tiêu chí sáng tạo</title>
      <desc id={`${id}-description`}>Đồ vật: {reportItemsText(report)}. So sánh nhóm sử dụng ít AI và nhiều AI. Cột là trung bình theo người, thanh sai số ±1 SEM, p hiệu chỉnh Holm. Số liệu đầy đủ trong bảng ngay sau biểu đồ.</desc>
      <rect width="1000" height="630" fill="white" />
      <text x="500" y="36" textAnchor="middle" fontSize="24" fill="#1c1917">Điểm trung bình theo bốn tiêu chí sáng tạo</text>
      <text x="500" y="61" textAnchor="middle" fontSize="13" fill="#57534e">{context} · Điểm chính thức · Thanh sai số ±1 SEM</text>
      {(["LOW", "HIGH"] as const).map((group, index) => (
        <g key={group}>
          <rect x={305 + index * 230} y="80" width="13" height="13" fill={GROUP_COLORS[group]} />
          <text x={325 + index * 230} y="91" fontSize="14" fill="#1c1917">
            {GROUP_LABELS[group]} (n = {group === "LOW" ? report.sample.score_participants_low : report.sample.score_participants_high})
          </text>
        </g>
      ))}
      {[0, 1, 2, 3, 4].map(tick => (
        <g key={tick}>
          <line x1={left} y1={y(ceiling * tick / 4)} x2={width - right} y2={y(ceiling * tick / 4)} stroke={tick === 0 ? "#78716c" : "#e7e5e4"} />
          <text x={left - 14} y={y(ceiling * tick / 4) + 5} textAnchor="end" fontSize="13" fill="#57534e">{ceiling * tick / 4}</text>
        </g>
      ))}
      {dimensions.map((row, index) => {
        const center = left + step * (index + 0.5);
        const peak = Math.max((row.low.mean ?? 0) + (row.low.sem ?? 0), (row.high.mean ?? 0) + (row.high.sem ?? 0));
        const bracket = y(peak) - 26;
        return (
          <g key={row.dimension}>
            {([row.low, row.high]).map((estimate, groupIndex) => {
              const x = center - 51 + groupIndex * 58;
              const color = groupIndex === 0 ? GROUP_COLORS.LOW : GROUP_COLORS.HIGH;
              if (estimate.mean === null) return <text key={groupIndex} x={x + 22} y={bottom - 12} fontSize="11" textAnchor="middle" fill="#78716c">Chưa có</text>;
              const upper = y(estimate.mean + (estimate.sem ?? 0));
              const lower = y(estimate.mean - (estimate.sem ?? 0));
              return (
                <g key={groupIndex}>
                  <title>{groupIndex === 0 ? GROUP_LABELS.LOW : GROUP_LABELS.HIGH}: {scoreText(estimate.mean)}; SEM {scoreText(estimate.sem)}; n = {estimate.n}</title>
                  <rect x={x} y={y(estimate.mean)} width="44" height={bottom - y(estimate.mean)} fill={color} />
                  {estimate.mean === 0 ? <line x1={x} x2={x + 44} y1={bottom - 1} y2={bottom - 1} stroke={color} strokeWidth="3" /> : null}
                  {estimate.sem !== null ? <g stroke="#1c1917" strokeWidth="2">
                    <line x1={x + 22} y1={upper} x2={x + 22} y2={lower} />
                    <line x1={x + 15} y1={upper} x2={x + 29} y2={upper} />
                    <line x1={x + 15} y1={lower} x2={x + 29} y2={lower} />
                  </g> : null}
                </g>
              );
            })}
            {row.p_value_holm !== null ? <g fill="none" stroke="#57534e">
              <path d={`M ${center - 29} ${bracket + 7} V ${bracket} H ${center + 29} V ${bracket + 7}`} />
              <text x={center} y={bracket - 9} textAnchor="middle" fontSize="13" fill="#1c1917" stroke="none">p {row.p_value_holm < 0.0001 ? "" : "= "}{pText(row.p_value_holm)}</text>
            </g> : null}
          </g>
        );
      })}
      <g fontSize="14" fill="#1c1917">
        <rect x="70" y="446" width="900" height="114" fill="white" stroke="#d6d3d1" />
        {[0, 1, 2].map(index => <line key={index} x1="70" x2="970" y1={484 + index * 38} y2={484 + index * 38} stroke="#d6d3d1" />)}
        {dimensions.map((row, index) => {
          const center = left + step * (index + 0.5);
          return <g key={row.dimension}>
            {index > 0 ? <line x1={left + step * index} x2={left + step * index} y1="446" y2="560" stroke="#d6d3d1" /> : null}
            <text x={center} y="471" textAnchor="middle" fontWeight="bold">{DIMENSION_LABELS[row.dimension]}</text>
            <text x={center} y="509" textAnchor="middle" fill={GROUP_COLORS.LOW}>{scoreText(row.low.mean)}</text>
            <text x={center} y="547" textAnchor="middle" fill="#9c4f1b">{scoreText(row.high.mean)}</text>
          </g>;
        })}
      </g>
      <text x="500" y="588" fontSize="12" textAnchor="middle" fill="#57534e">Hàng xanh: sử dụng ít AI · Hàng cam: sử dụng nhiều AI · p trên biểu đồ đã hiệu chỉnh Holm</text>
      <text x="500" y="610" fontSize="12" textAnchor="middle" fill="#57534e">Dấu —: chưa có điểm; không vẽ sai số khi n &lt; 2. Bộ đồ vật có thể khác nhau giữa người tham gia.</text>
    </svg>
  );
}
