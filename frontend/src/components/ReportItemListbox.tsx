import { useState, type KeyboardEvent } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Item } from "@/lib/types";

export function ReportItemListbox({ items, selectedIds, onChange }: {
  items: Item[];
  selectedIds: string[] | null;
  onChange: (ids: string[] | null) => void;
}) {
  const [focusedIndex, setFocusedIndex] = useState(0);
  const selected = new Set(selectedIds ?? items.map(item => item.id));

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = event.key === "ArrowDown" ? Math.min(index + 1, items.length - 1)
      : event.key === "ArrowUp" ? Math.max(index - 1, 0)
      : event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("[role=option]")[next]?.focus();
  }

  return <div className="w-full space-y-2 text-sm sm:w-80">
    <div className="flex items-center justify-between gap-3">
      <span id="report-items-label" className="font-medium">Đồ vật</span>
      <span className="font-mono text-xs text-muted-foreground">{selected.size}/{items.length} đã chọn</span>
    </div>
    <div className="flex gap-2">
      <Button size="sm" variant="outline" disabled={!items.length} onClick={() => onChange(null)}>Chọn tất cả</Button>
      <Button size="sm" variant="ghost" disabled={!selected.size} onClick={() => onChange([])}>Bỏ chọn hết</Button>
    </div>
    <div role="listbox" aria-labelledby="report-items-label" aria-multiselectable="true"
      className="max-h-56 overflow-y-auto rounded-md border border-input bg-card p-1">
      {items.map((item, index) => <button key={item.id} type="button" role="option"
        aria-selected={selected.has(item.id)} tabIndex={index === focusedIndex ? 0 : -1}
        onFocus={() => setFocusedIndex(index)} onKeyDown={event => moveFocus(event, index)}
        onClick={() => onChange(items.filter(value => value.id === item.id ? !selected.has(value.id) : selected.has(value.id)).map(value => value.id))}
        className="flex w-full items-center gap-3 rounded-sm px-3 py-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring aria-selected:bg-stone-100">
        <span aria-hidden="true" className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border ${selected.has(item.id) ? "border-stone-800 bg-stone-800 text-white" : "border-stone-400"}`}>
          {selected.has(item.id) ? <Check className="h-3 w-3" /> : null}
        </span>
        {item.name}
      </button>)}
      {!items.length ? <p className="px-3 py-3 text-muted-foreground">Chưa có đồ vật.</p> : null}
    </div>
    <p className="text-xs text-muted-foreground">Bấm từng mục để chọn hoặc bỏ chọn nhiều đồ vật.</p>
  </div>;
}
