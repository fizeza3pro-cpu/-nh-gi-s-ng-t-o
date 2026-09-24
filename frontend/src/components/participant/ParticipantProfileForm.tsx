import { useState, type FormEvent } from "react";
import {
  ArrowRight,
  Fingerprint,
  Loader2,
  Mail,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type {
  AiUsageGroup,
  ParticipantGender,
  ParticipantIdentity,
  ParticipantProfile,
} from "@/lib/types";

const GENDER_OPTIONS: Array<{ value: ParticipantGender; label: string }> = [
  { value: "male", label: "Nam" },
  { value: "female", label: "Nữ" },
  { value: "other", label: "Khác" },
  { value: "prefer_not_to_say", label: "Không muốn trả lời" },
];

const AI_USAGE_OPTIONS: Array<{
  value: AiUsageGroup;
  label: string;
  description: string;
}> = [
  {
    value: "LOW",
    label: "Ít sử dụng",
    description:
      "Tôi không sử dụng hoặc chỉ thỉnh thoảng sử dụng AI trong học tập, công việc.",
  },
  {
    value: "HIGH",
    label: "Sử dụng nhiều",
    description:
      "Tôi thường xuyên sử dụng AI như một công cụ hỗ trợ trong học tập, công việc.",
  },
];

const fieldClassName =
  "h-11 w-full rounded-lg border border-input bg-background px-3.5 text-sm outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-foreground/40 focus:ring-2 focus:ring-ring";

export default function ParticipantProfileForm({
  onComplete,
}: {
  onComplete: (participant: ParticipantIdentity) => void;
}) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<ParticipantGender | "">("");
  const [occupation, setOccupation] = useState("");
  const [aiUsageGroup, setAiUsageGroup] = useState<AiUsageGroup | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const emailReady = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  const profileReady =
    emailReady &&
    fullName.trim().length >= 2 &&
    Number(age) >= 10 &&
    Number(age) <= 100 &&
    gender !== "" &&
    occupation.trim().length >= 2 &&
    aiUsageGroup !== "";

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profileReady || submitting || !gender || !aiUsageGroup) return;

    const profile: ParticipantProfile = {
      full_name: fullName.trim(),
      age: Number(age),
      gender,
      occupation: occupation.trim(),
      ai_usage_group: aiUsageGroup,
    };
    setSubmitting(true);
    setError(null);
    try {
      const participant = await api.createParticipant(email.trim(), profile);
      onComplete(participant);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Không thể lưu thông tin. Hãy thử lại.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="grid lg:grid-cols-[0.72fr_1.28fr]">
        <div className="border-b border-border bg-foreground p-7 text-background lg:border-b-0 lg:border-r lg:p-9">
          <Fingerprint
            className="h-8 w-8 text-background/80"
            strokeWidth={1.5}
          />
          <h2 className="mt-8 max-w-xs font-serif text-3xl leading-tight">
            Thông tin người tham gia
          </h2>
          <p className="mt-4 max-w-sm text-sm leading-6 text-background/70">
            Hoàn thành một biểu mẫu duy nhất trước khi bắt đầu bài khảo sát AUT.
          </p>

          <div className="mt-8 border-t border-background/20 pt-5">
            <div className="flex gap-3 text-sm leading-6 text-background/75">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
              <p>
                Email chỉ được lưu dưới dạng mã tra cứu và bản che một phần.
                Nhóm sử dụng AI phục vụ thống kê nghiên cứu.
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={handleProfileSubmit} className="p-7 lg:p-9">
          <div className="max-w-2xl">
            <h3 className="font-serif text-2xl">Hồ sơ khảo sát</h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Điền thông tin và chọn mức sử dụng AI phù hợp nhất với bạn.
            </p>

            <div className="mt-7 space-y-2">
              <label htmlFor="participant-email" className="text-sm font-medium">
                Email
              </label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="participant-email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  required
                  autoFocus
                  maxLength={320}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="ban@example.com"
                  className={`${fieldClassName} pl-10`}
                />
              </div>
            </div>

              <div className="mt-7 space-y-2">
                <label
                  htmlFor="participant-full-name"
                  className="text-sm font-medium"
                >
                  Họ và tên
                </label>
                <input
                  id="participant-full-name"
                  type="text"
                  autoComplete="name"
                  required
                  minLength={2}
                  maxLength={255}
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Ví dụ: Nguyễn Minh Anh"
                  className={fieldClassName}
                />
              </div>

              <div className="mt-6 grid gap-6 sm:grid-cols-[140px_1fr]">
                <div className="space-y-2">
                  <label
                    htmlFor="participant-age"
                    className="text-sm font-medium"
                  >
                    Tuổi
                  </label>
                  <input
                    id="participant-age"
                    type="number"
                    inputMode="numeric"
                    min={10}
                    max={100}
                    required
                    value={age}
                    onChange={(event) => setAge(event.target.value)}
                    placeholder="Ví dụ: 20"
                    className={fieldClassName}
                  />
                </div>

                <div className="space-y-2">
                  <label
                    htmlFor="participant-occupation"
                    className="text-sm font-medium"
                  >
                    Ngành học hoặc nghề nghiệp
                  </label>
                  <input
                    id="participant-occupation"
                    type="text"
                    required
                    minLength={2}
                    maxLength={255}
                    value={occupation}
                    onChange={(event) => setOccupation(event.target.value)}
                    placeholder="Ví dụ: Sinh viên Công nghệ thông tin"
                    className={fieldClassName}
                  />
                </div>
              </div>

              <fieldset className="mt-6">
                <legend className="text-sm font-medium">Giới tính</legend>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {GENDER_OPTIONS.map((option) => (
                    <label
                      key={option.value}
                      className={`flex min-h-11 cursor-pointer items-center gap-2.5 rounded-lg border px-3 text-sm transition-colors focus-within:ring-2 focus-within:ring-ring ${
                        gender === option.value
                          ? "border-foreground bg-foreground text-background"
                          : "border-input bg-background hover:bg-muted/50"
                      }`}
                    >
                      <input
                        type="radio"
                        name="participant-gender"
                        value={option.value}
                        checked={gender === option.value}
                        onChange={() => setGender(option.value)}
                        className="sr-only"
                      />
                      <span
                        className={`h-2 w-2 shrink-0 rounded-full ${gender === option.value ? "bg-background" : "border border-foreground/40"}`}
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              </fieldset>

              <fieldset className="mt-7 border-t border-border pt-6">
                <legend className="pr-3 text-sm font-medium">
                  Mức độ sử dụng AI trong học tập hoặc công việc
                </legend>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {AI_USAGE_OPTIONS.map((option) => (
                    <label
                      key={option.value}
                      className={`cursor-pointer rounded-xl border p-4 transition-colors focus-within:ring-2 focus-within:ring-ring ${
                        aiUsageGroup === option.value
                          ? "border-foreground bg-foreground text-background"
                          : "border-input bg-background hover:bg-muted/50"
                      }`}
                    >
                      <input
                        type="radio"
                        name="participant-ai-usage"
                        value={option.value}
                        checked={aiUsageGroup === option.value}
                        onChange={() => setAiUsageGroup(option.value)}
                        className="sr-only"
                      />
                      <span className="text-sm font-semibold">{option.label}</span>
                      <span
                        className={`mt-1.5 block text-xs leading-5 ${
                          aiUsageGroup === option.value
                            ? "text-background/75"
                            : "text-muted-foreground"
                        }`}
                      >
                        {option.description}
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              {error && (
                <p
                  className="mt-5 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
                  role="alert"
                >
                  {error}
                </p>
              )}

              <div className="mt-7 flex flex-col gap-3 border-t border-border pt-6 sm:flex-row sm:items-center sm:justify-between">
                <p className="max-w-xs text-xs leading-5 text-muted-foreground">
                  Tiếp tục đồng nghĩa với việc bạn đồng ý dùng câu trả lời cho
                  mục đích thống kê nghiên cứu.
                </p>
                <Button
                  type="submit"
                  size="lg"
                  disabled={!profileReady || submitting}
                  className="shrink-0 sm:min-w-52"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> Đang lưu
                      thông tin
                    </>
                  ) : (
                    <>
                      Lưu và bắt đầu <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </Button>
              </div>
          </div>
        </form>
      </div>
    </section>
  );
}
