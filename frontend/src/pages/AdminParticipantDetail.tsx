import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Inbox } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { AdminParticipantDetail as AdminParticipantDetailType } from "@/lib/types";

const GENDER_LABELS: Record<string, string> = {
  male: "Nam",
  female: "Nữ",
  other: "Khác",
  prefer_not_to_say: "Không trả lời",
};

function fmtDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AdminParticipantDetail() {
  const { participantId } = useParams<{ participantId: string }>();
  const [detail, setDetail] = useState<AdminParticipantDetailType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!participantId) return;
    setDetail(null);
    setError(null);
    api
      .adminParticipantDetail(participantId)
      .then(setDetail)
      .catch((err: Error) => setError(err.message));
  }, [participantId]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 animate-fade-in">
      <Link
        to="/admin/participants"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại danh sách người tham gia
      </Link>

      {error && (
        <p className="mt-6 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </p>
      )}

      {!detail && !error && (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-5 w-40" />
        </div>
      )}

      {detail && (
        <div className="mb-6 mt-6">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-serif text-2xl font-medium tracking-tight">
              {detail.participant.email_masked || "Người tham gia"}
            </h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {detail.participant.age ?? "—"} tuổi · {detail.participant.gender ? GENDER_LABELS[detail.participant.gender] ?? detail.participant.gender : "Dữ liệu cũ"} · {detail.participant.occupation || "Chưa có ngành/nghề"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Email: {detail.participant.email_masked || "Chưa liên kết email"} · {detail.participant.email_verified_at ? "Đã xác thực" : "Chưa xác thực"}
          </p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            Tham gia {fmtDate(detail.participant.created_at)}
          </p>
        </div>
      )}

      {detail && (
        <>
          <h2 className="mb-3 text-sm font-semibold text-foreground">
            Lịch sử trả lời · {detail.responses.length} lượt
          </h2>

          {detail.responses.length === 0 && (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-card py-16 text-center">
              <Inbox className="h-7 w-7 text-muted-foreground" />
              <p className="text-muted-foreground">
                Người này chưa nộp lượt nào.
              </p>
            </div>
          )}

          {detail.responses.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Thời gian</th>
                    <th className="px-4 py-3 font-medium">Đồ vật</th>
                    <th className="px-4 py-3 text-right font-medium">Số ý</th>
                    <th className="px-4 py-3 text-right font-medium">Đa dạng</th>
                    <th className="px-4 py-3 text-right font-medium">Độc đáo</th>
                    <th className="px-4 py-3 text-right font-medium">Chi tiết</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {detail.responses.map((r) => (
                    <tr
                      key={r.response_id}
                      className="transition-colors hover:bg-muted/30"
                    >
                      <td className="whitespace-nowrap px-4 py-3.5 font-mono text-xs text-muted-foreground">
                        {fmtDate(r.created_at)}
                      </td>
                      <td className="px-4 py-3.5 font-medium">{r.item_name}</td>
                      <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                        {r.fluency}
                      </td>
                      <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                        {r.flexibility}
                      </td>
                      <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                        {r.originality}
                      </td>
                      <td className="px-4 py-3.5 text-right font-mono tabular-nums">
                        {r.elaboration}
                      </td>
                      <td className="px-4 py-3.5 text-right">
                        <Link
                          to={`/result/${r.response_id}`}
                          className="inline-flex items-center gap-1 text-sm font-medium text-foreground/80 hover:text-foreground"
                        >
                          Xem <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
