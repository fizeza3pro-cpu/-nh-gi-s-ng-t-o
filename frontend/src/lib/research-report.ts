import type { AdminResearchReport, ReportScoreDimension } from "@/lib/report-types";

export const GROUP_LABELS = {
  LOW: "Sử dụng ít AI", HIGH: "Sử dụng nhiều AI", UNKNOWN: "Chưa khai báo nhóm",
};
export const DIMENSION_LABELS: Record<ReportScoreDimension["dimension"], string> = {
  originality: "Độc đáo", flexibility: "Linh hoạt", fluency: "Trôi chảy", elaboration: "Chi tiết",
};
export const GROUP_COLORS = { LOW: "#456fb0", HIGH: "#d97832" };
export const numberText = (value: number) => value.toLocaleString("vi-VN");
export const scoreText = (value: number | null) => value === null ? "—" : value.toLocaleString("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const pText = (value: number | null) => value === null ? "Chưa đủ dữ liệu" : value < 0.0001 ? "< 0,0001" : value.toLocaleString("vi-VN", { minimumFractionDigits: 4, maximumFractionDigits: 4 });

export function reportItemsText(report: AdminResearchReport, compact = false) {
  const ids = report.item_ids;
  if (!ids.length) return "Tất cả đồ vật";
  if (compact && ids.length > 1) return `${ids.length} đồ vật đã chọn`;
  return report.available_items.filter(item => ids.includes(item.id)).map(item => item.name).join(", ");
}

export function downloadReportFile(content: BlobPart, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadReportCsv(report: AdminResearchReport) {
  const rows: (string | number | null)[][] = [
    ["Báo cáo AUT", "So sánh sử dụng ít AI / sử dụng nhiều AI"],
    ["Nguồn", report.data_source], ["Thời điểm", report.generated_at],
    ["Đồ vật", reportItemsText(report)],
    [], ["Mẫu dữ liệu", "Số lượt"],
    ...Object.entries(report.sample).map(([key, value]) => [key, value]),
    [], ["Bảng 1. Ý tưởng theo đồ vật và nhóm"],
    ["Đồ vật", "Nhóm", "Số người", "Số lượt", "Tổng ý", "Hợp lệ", "Không hợp lệ", "Trùng lặp", "Chưa phân loại", "Hợp lệ chờ mã"],
    ...report.object_groups.map(row => [row.item_name, GROUP_LABELS[row.group], row.participant_count, row.response_count, row.total_ideas, row.valid_ideas, row.invalid_ideas, row.duplicate_ideas, row.unclassified_ideas, row.pending_code_ideas]),
    [], ["Bảng 2. Số mã đã sử dụng"],
    ["Đồ vật", "Sử dụng ít AI", "Sử dụng nhiều AI", "Chung hai nhóm", "Tổng mã (kể cả chưa khai báo)"],
    ...report.object_codes.map(row => [row.item_name, row.low_code_count, row.high_code_count, row.shared_code_count, row.total_code_count]),
    [], ["Bảng 3. Điểm trung bình theo người tham gia"],
    ["Tiêu chí", "Nhóm", "n", "Trung bình", "SD", "SEM", "Chênh lệch nhiều - ít", "p Welch thô", "p Holm", "Ghi chú"],
    ...report.dimensions.flatMap(row => (["LOW", "HIGH"] as const).map(group => {
      const estimate = group === "LOW" ? row.low : row.high;
      return [DIMENSION_LABELS[row.dimension], GROUP_LABELS[group], estimate.n, estimate.mean, estimate.sd, estimate.sem, row.difference, row.p_value, row.p_value_holm, row.test_note];
    })),
    [], ["Nhận xét"], ...report.summary_vi.map(line => [line]),
    [], ["Phương pháp"], ...report.methodology_vi.map(line => [line]),
  ];
  const csv = rows.map(row => row.map(value => {
    let cell = value === null ? "" : String(value);
    if (typeof value === "string" && /^[=+@\-\t\r]/.test(cell)) cell = `'${cell}`;
    return `"${cell.replace(/"/g, '""')}"`;
  }).join(",")).join("\r\n");
  downloadReportFile(`\ufeff${csv}`, "aut-bao-cao-nghom-ai.csv", "text/csv;charset=utf-8");
}
