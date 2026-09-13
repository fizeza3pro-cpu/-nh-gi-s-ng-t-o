import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { AdminParticipantSummary } from "@/lib/types";

const GENDER_LABELS: Record<string, string> = {
  male: "Nam",
  female: "Nữ",
  other: "Khác",
  prefer_not_to_say: "Không trả lời",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "Chưa nộp bài";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AdminParticipants() {
  const [participants, setParticipants] = useState<AdminParticipantSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .adminListParticipants()
      .then(setParticipants)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 animate-fade-in">
      <div className="mb-6">
        <h1 className="font-serif text-2xl font-medium tracking-tight">
          Người tham gia
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Mỗi hồ sơ được nhận diện bằng email tự khai; phiên bản hiện tại chưa xác thực email.
        </p>
      </div>

      {error && (
        <p className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </p>
      )}

      {!participants && !error && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {participants && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Email định danh</th>
                <th className="px-4 py-3 font-medium">Tuổi</th>
                <th className="px-4 py-3 font-medium">Giới tính</th>
                <th className="px-4 py-3 font-medium">Ngành / nghề</th>
                <th className="px-4 py-3 text-right font-medium">
                  Số lượt nộp
                </th>
                <th className="px-4 py-3 font-medium">Lần nộp gần nhất</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {participants.map((participant) => (
                <tr key={participant.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3.5">
                    <p className="font-mono text-xs">{participant.email_masked || "Chưa liên kết"}</p>
                    <p className="mt-1 text-[11px] text-amber-700">
                      {participant.email_verified_at ? "Đã xác thực" : "Chưa xác thực"}
                    </p>
                  </td>
                  <td className="px-4 py-3.5">{participant.age ?? "—"}</td>
                  <td className="px-4 py-3.5">
                    {participant.gender ? GENDER_LABELS[participant.gender] ?? participant.gender : "—"}
                  </td>
                  <td className="px-4 py-3.5 font-medium">{participant.occupation || "Dữ liệu cũ"}</td>
                  <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                    {participant.response_count}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3.5 font-mono text-xs text-muted-foreground">
                    {fmtDate(participant.last_submitted_at)}
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <Link
                      to={`/admin/participants/${participant.id}`}
                      className="inline-flex items-center gap-1 text-sm font-medium text-foreground/80 hover:text-foreground"
                    >
                      Chi tiết <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </td>
                </tr>
              ))}
              {participants.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-4 py-8 text-center text-muted-foreground"
                  >
                    Chưa có người tham gia nào.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
