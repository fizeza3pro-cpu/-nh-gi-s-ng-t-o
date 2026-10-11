import { useEffect, useRef, useState } from "react";
import { Download, Printer, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ResearchScoreChart } from "@/components/charts/ResearchScoreChart";
import { ReportItemListbox } from "@/components/ReportItemListbox";
import { api } from "@/lib/api";
import type { Item } from "@/lib/types";
import type { AdminResearchReport } from "@/lib/report-types";
import { DIMENSION_LABELS, GROUP_COLORS, GROUP_LABELS, downloadReportCsv, downloadReportFile, numberText, pText, reportItemsText, scoreText } from "@/lib/research-report";

const numericCell = "px-3 py-3 text-right font-mono tabular-nums";
const headerCell = "px-3 py-3 text-right font-medium";
const sampleLabels: [keyof AdminResearchReport["sample"], string][] = [
  ["submitted_responses", "Lượt đã thu thập"], ["analyzed_responses", "Lượt được tổng hợp"],
  ["excluded_responses", "Lượt bị loại"], ["unfinished_responses", "Lượt đang xử lý"],
  ["failed_responses", "Lượt xử lý lỗi"], ["ungrouped_responses", "Lượt chưa khai báo nhóm"],
  ["final_scored_responses", "Lượt dùng so sánh điểm"], ["stale_score_responses", "Lượt có điểm chờ đồng bộ"],
];

export default function AdminReports() {
  const [report, setReport] = useState<AdminResearchReport | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [source, setSource] = useState("");
  const [selectedItemIds, setSelectedItemIds] = useState<string[] | null>(null);
  const filterKey = selectedItemIds === null ? "" : JSON.stringify([...selectedItemIds].sort());
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setReport(null);
    if (filterKey === "[]") {
      setLoading(false);
      return () => controller.abort();
    }
    api.adminResearchReport({ source, itemIds: filterKey ? JSON.parse(filterKey) as string[] : undefined, signal: controller.signal }).then(data => {
      if (controller.signal.aborted) return;
      setReport(data);
      setItems(data.available_items);
    }).catch(err => {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Không thể tải báo cáo.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [source, filterKey, revision]);

  function downloadChart() {
    if (!svgRef.current) return;
    const svg = new XMLSerializer().serializeToString(svgRef.current);
    downloadReportFile(svg, "aut-diem-trung-binh-nghom-ai.svg", "image/svg+xml;charset=utf-8");
  }

  return (
    <div className="research-report mx-auto max-w-6xl space-y-8 px-5 py-8 sm:px-6 lg:py-10">
      <header className="border-b border-stone-300 pb-6">
        <h1 className="font-serif text-3xl tracking-tight sm:text-4xl">Báo cáo kết quả khảo sát</h1>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          Tổng hợp ý tưởng, danh mục công dụng và điểm sáng tạo của hai nhóm sử dụng ít AI và sử dụng nhiều AI.
        </p>
        <div className="report-controls mt-5 flex flex-wrap gap-2">
          <Button variant="outline" disabled={!report || loading} onClick={() => report && downloadReportCsv(report)}><Download className="h-4 w-4" />Xuất bảng CSV</Button>
          <Button variant="outline" disabled={!report || loading} onClick={() => window.print()}><Printer className="h-4 w-4" />In / Lưu PDF</Button>
          <Button variant="ghost" disabled={loading} onClick={() => setRevision(value => value + 1)}><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />Cập nhật</Button>
        </div>
      </header>

      <div className="report-controls flex flex-wrap gap-4 border-b border-border pb-6">
        <div className="space-y-2 text-sm"><label htmlFor="report-source" className="block font-medium">Nguồn dữ liệu</label>
          <select id="report-source" value={source} onChange={event => setSource(event.target.value)} className="h-10 rounded-md border border-input bg-card px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <option value="">Nguồn hiện hành</option>
            <option value="PILOT">Dữ liệu PILOT</option>
            <option value="SURVEY">Dữ liệu SURVEY</option>
          </select>
          <p className="max-w-64 text-xs leading-relaxed text-muted-foreground">PILOT và SURVEY là nhãn nguồn lưu trong database. Nguồn hiện hành theo cấu hình SURVEY_DATA_SOURCE; không gồm SYNTHETIC.</p>
        </div>
        <ReportItemListbox items={items} selectedIds={selectedItemIds} onChange={setSelectedItemIds} />
      </div>

      {filterKey === "[]" ? <p role="status" className="border border-border bg-muted/40 p-5 text-sm">Chọn ít nhất một đồ vật để thống kê.</p> : null}
      {loading ? <p role="status" className="py-12 text-center text-muted-foreground">Đang tổng hợp dữ liệu khảo sát…</p> : null}
      {error ? <div role="alert" className="border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error} <Button variant="ghost" size="sm" onClick={() => setRevision(value => value + 1)}>Thử lại</Button></div> : null}
      {report ? <>
        <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
          <p>Nguồn: <strong>{report.data_source}</strong> · {reportItemsText(report)}</p>
          <p>Lập lúc {new Date(report.generated_at).toLocaleString("vi-VN", { timeZone: "Asia/Bangkok" })}</p>
        </div>
        {report.sample.submitted_responses === 0 ? <p className="border border-border bg-muted/40 p-5 text-sm">Chưa có lượt trả lời cho nguồn và đồ vật này. Chọn nguồn khác hoặc tiếp tục thu thập khảo sát.</p> : null}

        <section aria-labelledby="report-summary">
          <h2 id="report-summary" className="font-serif text-2xl">Tổng hợp dữ liệu</h2>
          <ul className="mt-4 space-y-2 text-sm leading-relaxed">{report.summary_vi.map(line => <li key={line}>{line}</li>)}</ul>
          <div className="report-table mt-5 overflow-x-auto">
            <table className="w-full min-w-[550px] border-y border-border text-sm">
              <thead className="border-b border-border"><tr>
                <th scope="col" className="px-3 py-3 text-left font-medium">Nhóm</th>
                {["Hồ sơ toàn hệ thống", "Đã nộp trong phạm vi chọn", "Có điểm dùng biểu đồ"].map(label => <th key={label} scope="col" className={headerCell}>{label}</th>)}
              </tr></thead>
              <tbody>{(["LOW", "HIGH"] as const).map(group => {
                const suffix = group === "LOW" ? "low" : "high";
                return <tr key={group}><th scope="row" className="px-3 py-3 text-left font-medium">{GROUP_LABELS[group]}</th>
                  <td className={numericCell}>{report.sample[`registered_participants_${suffix}`]}</td>
                  <td className={numericCell}>{report.sample[`submitted_participants_${suffix}`]}</td>
                  <td className={numericCell}>{report.sample[`score_participants_${suffix}`]}</td>
                </tr>;
              })}</tbody>
            </table>
          </div>
          <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-y border-border py-4 text-sm sm:grid-cols-4">
            {sampleLabels.map(([key, label]) => <div key={key}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-mono text-xl tabular-nums">{numberText(report.sample[key])}</dd></div>)}
          </dl>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Có {numberText(report.sample.other_source_responses)} lượt thuộc nguồn khác hoặc dữ liệu mô phỏng được giữ ngoài báo cáo này. Các lượt chưa có điểm vẫn góp vào bảng ý tưởng sau khi xử lý hoàn tất.</p>
          {report.sample.stale_score_responses > 0 ? <p className="mt-3 border-l-2 border-amber-600 pl-3 text-sm text-amber-900">Có điểm đang chờ đồng bộ với codebook. Các điểm này được tạm giữ ngoài biểu đồ; cập nhật báo cáo sau khi hệ thống đồng bộ xong.</p> : null}
        </section>

        <section aria-labelledby="report-ideas">
          <h2 id="report-ideas" className="font-serif text-xl sm:text-2xl">Bảng 1. Số ý tưởng theo đồ vật và nhóm sử dụng AI</h2>
          <div className="report-table mt-4 overflow-x-auto">
            <table className="w-full min-w-[950px] border-y-2 border-foreground text-sm">
              <thead className="border-b-2 border-foreground"><tr>
                <th scope="col" className="px-3 py-3 text-left font-medium">Đồ vật</th><th scope="col" className="px-3 py-3 text-left font-medium">Nhóm</th>
                {["Số người", "Số lượt", "Tổng ý", "Hợp lệ", "Không hợp lệ", "Trùng lặp", "Chưa phân loại", "Hợp lệ chờ mã"].map(label => <th key={label} scope="col" className={headerCell}>{label}</th>)}
              </tr></thead>
              <tbody>{report.object_groups.map((row, index) => <tr key={`${row.item_id}-${row.group}`} className={index > 0 && report.object_groups[index - 1].item_id !== row.item_id ? "border-t border-dashed border-stone-400" : ""}>
                <th scope="row" className="px-3 py-3 text-left font-serif text-base font-semibold">{row.item_name}</th>
                <td className="whitespace-nowrap px-3 py-3">{GROUP_LABELS[row.group]}</td>
                {[row.participant_count, row.response_count, row.total_ideas, row.valid_ideas, row.invalid_ideas, row.duplicate_ideas, row.unclassified_ideas, row.pending_code_ideas].map((value, i) => <td key={i} className={numericCell}>{numberText(value)}</td>)}
              </tr>)}</tbody>
              <tfoot className="border-t-2 border-foreground font-semibold"><tr><th scope="row" colSpan={2} className="px-3 py-3 text-left">Tổng toàn mẫu</th>
                {[report.totals.participant_count, report.totals.response_count, report.totals.total_ideas, report.totals.valid_ideas, report.totals.invalid_ideas, report.totals.duplicate_ideas, report.totals.unclassified_ideas, report.totals.pending_code_ideas].map((value, index) => <td key={index} className={numericCell}>{numberText(value)}</td>)}
              </tr></tfoot>
            </table>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">“Số lượt” đếm bài nộp; “Tổng ý” đếm ý tưởng đã tách. Tổng ý = hợp lệ + không hợp lệ + trùng lặp + chưa phân loại. “Hợp lệ chờ mã” nằm trong “Hợp lệ”. Tổng số người đếm người duy nhất trong toàn mẫu, không cộng các dòng đồ vật.</p>
        </section>

        <section aria-labelledby="report-codes">
          <h2 id="report-codes" className="font-serif text-xl sm:text-2xl">Bảng 2. Số mã dùng để phân loại ý hợp lệ</h2>
          <div className="report-table mt-4 overflow-x-auto">
            <table className="w-full min-w-[650px] border-y-2 border-foreground text-sm">
              <thead className="border-b-2 border-foreground"><tr><th scope="col" className="px-3 py-3 text-left font-medium">Đồ vật</th>
                {["Sử dụng ít AI", "Sử dụng nhiều AI", "Chung hai nhóm", "Tổng mã"].map(label => <th key={label} scope="col" className={headerCell}>{label}</th>)}
              </tr></thead>
              <tbody>{report.object_codes.map(row => <tr key={row.item_id} className="border-b border-border last:border-0"><th scope="row" className="px-3 py-3 text-left font-serif text-base font-semibold">{row.item_name}</th>
                {[row.low_code_count, row.high_code_count, row.shared_code_count, row.total_code_count].map((value, i) => <td key={i} className={numericCell}>{numberText(value)}</td>)}
              </tr>)}</tbody>
            </table>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Chỉ đếm mã được chấp nhận, đang hoạt động và đã xuất hiện ở ý hợp lệ. Mã chung hai nhóm được tính một lần trong tổng; tổng cũng bao gồm mã của người chưa khai báo nhóm.</p>
        </section>

        <section aria-labelledby="report-chart" className="report-chart-section">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="report-chart" className="font-serif text-xl sm:text-2xl">Hình 1. So sánh điểm sáng tạo giữa hai nhóm</h2>
            <Button className="report-controls" variant="outline" size="sm" onClick={downloadChart}><Download className="h-4 w-4" />Tải biểu đồ SVG</Button>
          </div>
          {report.sample.final_scored_responses === 0 ? <p className="mt-4 border-l-2 border-stone-400 pl-3 text-sm text-muted-foreground">Chưa có điểm chính thức đủ điều kiện để so sánh. Bảng ý tưởng và mã phía trên vẫn phản ánh dữ liệu đã thu thập.</p> : null}
          <figure className="report-chart mt-4 overflow-x-auto border border-stone-300 bg-white p-2 sm:p-4"><ResearchScoreChart report={report} svgRef={svgRef} /></figure>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Cột = điểm trung bình theo người; thanh sai số = ±1 SEM; n = số người có điểm. p trên biểu đồ đã hiệu chỉnh Holm cho bốn tiêu chí. Xem từng đồ vật để đối chiếu khi hai nhóm làm các đồ vật khác nhau.</p>
        </section>

        <section aria-labelledby="report-scores">
          <h2 id="report-scores" className="font-serif text-xl sm:text-2xl">Bảng 3. Điểm trung bình và kiểm định khác biệt</h2>
          <div className="report-table mt-4 overflow-x-auto">
            <table className="w-full min-w-[850px] border-y-2 border-foreground text-sm">
              <thead className="border-b-2 border-foreground"><tr><th scope="col" className="px-3 py-3 text-left font-medium">Tiêu chí</th><th scope="col" className="px-3 py-3 text-left font-medium">Nhóm</th>
                {["n", "Trung bình", "SD", "SEM", "Nhiều − ít", "p thô", "p Holm"].map(label => <th key={label} scope="col" className={headerCell}>{label}</th>)}
              </tr></thead>
              <tbody>{report.dimensions.flatMap(row => (["LOW", "HIGH"] as const).map((group, index) => {
                const score = group === "LOW" ? row.low : row.high;
                return <tr key={`${row.dimension}-${group}`} className={index === 0 ? "border-t border-dashed border-stone-400" : ""}>
                  {index === 0 ? <th rowSpan={2} scope="rowgroup" className="px-3 py-3 text-left font-serif text-base">{DIMENSION_LABELS[row.dimension]}</th> : null}
                  <td className="whitespace-nowrap px-3 py-3"><span className="mr-2 inline-block h-2.5 w-2.5" style={{ background: GROUP_COLORS[group] }} />{GROUP_LABELS[group]}</td>
                  <td className={numericCell}>{score.n}</td><td className={numericCell}>{scoreText(score.mean)}</td><td className={numericCell}>{scoreText(score.sd)}</td><td className={numericCell}>{scoreText(score.sem)}</td>
                  {index === 0 ? <><td rowSpan={2} className={numericCell}>{scoreText(row.difference)}</td><td rowSpan={2} className={numericCell} title={row.test_note}>{row.p_value === null ? "—" : pText(row.p_value)}</td><td rowSpan={2} className={numericCell} title={row.test_note}>{row.p_value_holm === null ? "—" : pText(row.p_value_holm)}</td></> : null}
                </tr>;
              }))}</tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">SD: độ lệch chuẩn mẫu. SEM: sai số chuẩn trung bình. Chênh lệch dương: nhóm sử dụng nhiều AI có điểm cao hơn. Dấu —: chưa ước lượng được.</p>
          {report.dimensions.filter(row => row.test_note).map(row => <p key={row.dimension} className="mt-2 text-xs text-muted-foreground">{DIMENSION_LABELS[row.dimension]}: {row.test_note}</p>)}
        </section>

        <section aria-labelledby="report-method" className="border-t border-border pt-6">
          <h2 id="report-method" className="font-serif text-xl">Cách tổng hợp và đọc kết quả</h2>
          <ol className="mt-4 list-decimal space-y-3 pl-5 text-sm leading-relaxed text-muted-foreground">{report.methodology_vi.map(line => <li key={line}>{line}</li>)}</ol>
        </section>
      </> : null}
    </div>
  );
}
