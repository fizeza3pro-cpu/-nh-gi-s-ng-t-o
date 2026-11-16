import type { Item } from "@/lib/types";

// Thứ tự và tên hiển thị của đồ vật; trạng thái ẩn/hiện do admin quản lý.
export const SURVEY_ITEMS = [
  { id: "vo_dan", name: "Vỏ đạn" },
  { id: "cuon_chi", name: "Kim chỉ" },
  { id: "xeng_cong_binh", name: "Xẻng công binh" },
  { id: "mu_coi", name: "Mũ cối" },
  { id: "balo_quan_nhu", name: "Ba lô" },
  { id: "bi_dong_nuoc", name: "Bi đông" },
  { id: "ghim_kep_giay", name: "Ghim kẹp giấy" },
  { id: "kinh_lup", name: "Kính lúp" },
] as const;

export function getSurveyItems(items: Item[], includeHidden = false): Item[] {
  const byId = new Map(items.map((item) => [item.id, item]));
  return SURVEY_ITEMS.flatMap(({ id, name }) => {
    const item = byId.get(id);
    return item && (includeHidden || item.survey_visible !== false)
      ? [{ ...item, name }]
      : [];
  });
}
