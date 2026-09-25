import { useEffect, useState } from "react";
import { ArrowRight, Clock3, UserRound } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, getParticipantIdentity } from "@/lib/api";
import type { ResponseSummary } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  COLLECTING: "Đang chờ đủ dữ liệu",
  PENDING_REVIEW: "Đang chờ đối chiếu",
  FINAL: "Đã có điểm",
  EXCLUDED: "Đã loại",
  PROVISIONAL: "Trạng thái cũ",
};

function formatDate(value: string): string {
  return new Date(value).toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default function History() {
  const participant = getParticipantIdentity();
  const [responses, setResponses] = useState<ResponseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!participant) return;
    api
      .participantResponses()
      .then(setResponses)
      .catch((err: Error) => setError(err.message));
  }, [participant?.id]);

  if (!participant) {
    return (
      <div className="container max-w-xl py-24 text-center">
        <UserRound className="mx-auto h-8 w-8 text-muted-foreground" />
        <h1 className="mt-5 font-serif text-3xl">Chưa có hồ sơ người tham gia</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          Chọn một đồ vật và điền thông tin để hệ thống nhận diện lịch sử của bạn.
        </p>
        <Button asChild className="mt-7">
          <Link to="/#chon-do-vat">Chọn đồ vật</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <section className="border-b border-border bg-muted/25">
        <div className="container max-w-5xl py-14 md:py-20">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <UserRound className="h-4 w-4" /> {participant.full_name}
          </div>
          <h1 className="mt-4 font-serif text-4xl md:text-5xl">Lịch sử khảo sát</h1>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground">
            Các lượt trả lời gắn với hồ sơ này. Lượt đang chờ sẽ tự cập nhật trên trang kết quả khi có quyết định.
          </p>
        </div>
      </section>

      <section className="container max-w-5xl py-10 md:py-14">
        {error && (
          <p className="border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </p>
        )}

        {!responses && !error && (
          <p className="py-16 text-center text-sm text-muted-foreground">Đang tải lịch sử…</p>
        )}

        {responses?.length === 0 && (
          <div className="border-l-2 border-border py-2 pl-6">
            <h2 className="font-serif text-2xl">Bạn chưa gửi bài khảo sát nào.</h2>
            <Button asChild variant="outline" className="mt-5">
              <Link to="/#chon-do-vat">Bắt đầu với một đồ vật</Link>
            </Button>
          </div>
        )}

        {responses && responses.length > 0 && (
          <ul className="divide-y divide-border border-y border-border">
            {responses.map((response) => {
              const final = response.scoring_status === "FINAL";
              return (
                <li key={response.response_id}>
                  <Link
                    to={`/result/${response.response_id}`}
                    className="grid gap-4 px-1 py-6 transition-colors hover:bg-muted/30 sm:grid-cols-[1fr_auto_auto] sm:items-center sm:px-4"
                  >
                    <div>
                      <p className="font-serif text-2xl">{response.item_name}</p>
                      <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                        <Clock3 className="h-3.5 w-3.5" /> {formatDate(response.created_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      <Badge variant={final ? "success" : "secondary"}>
                        {STATUS_LABEL[response.scoring_status] ?? response.scoring_status}
                      </Badge>
                      <p className="font-mono text-xs text-muted-foreground">
                        {final
                          ? `${response.fluency} / ${response.flexibility} / ${response.originality} / ${response.elaboration}`
                          : "Chưa có điểm"}
                      </p>
                    </div>
                    <ArrowRight className="hidden h-4 w-4 text-muted-foreground sm:block" />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
