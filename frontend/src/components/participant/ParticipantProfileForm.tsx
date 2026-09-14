import { useState, type FormEvent } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Fingerprint,
  Loader2,
  Mail,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type {
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

const fieldClassName =
  "h-11 w-full rounded-lg border border-input bg-background px-3.5 text-sm outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-foreground/40 focus:ring-2 focus:ring-ring";

export default function ParticipantProfileForm({
  onComplete,
}: {
  onComplete: (participant: ParticipantIdentity) => void;
}) {
  const [step, setStep] = useState<"EMAIL" | "PROFILE">("EMAIL");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<ParticipantGender | "">("");
  const [occupation, setOccupation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const emailReady = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  const profileReady =
    fullName.trim().length >= 2 &&
    Number(age) >= 10 &&
    Number(age) <= 100 &&
    gender !== "" &&
    occupation.trim().length >= 2;

  async function handleEmailSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!emailReady || submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      const result = await api.identifyParticipant(email.trim());
      if (result.profile_required) {
        setStep("PROFILE");
      } else if (result.participant) {
        onComplete(result.participant);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể kiểm tra email. Hãy thử lại.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profileReady || submitting || !gender) return;

    const profile: ParticipantProfile = {
      full_name: fullName.trim(),
      age: Number(age),
      gender,
      occupation: occupation.trim(),
    };
    setSubmitting(true);
    setError(null);
    try {
      const participant = await api.createParticipant(email.trim(), profile);
      onComplete(participant);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể lưu thông tin. Hãy thử lại.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="grid lg:grid-cols-[0.82fr_1.18fr]">
        <div className="border-b border-border bg-foreground p-7 text-background lg:border-b-0 lg:border-r lg:p-9">
          <Fingerprint className="h-8 w-8 text-background/80" strokeWidth={1.5} />
          <h2 className="mt-8 max-w-xs font-serif text-3xl leading-tight">
            Một email cho mọi lượt khảo sát
          </h2>
          <p className="mt-4 max-w-sm text-sm leading-6 text-background/70">
            Email giúp hệ thống nhận ra cùng một người khi đổi trình duyệt hoặc thiết bị, đồng thời
            vẫn lưu riêng từng lần trả lời.
          </p>

          <div className="mt-8 border-t border-background/20 pt-5">
            <div className="flex gap-3 text-sm leading-6 text-background/75">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
              <p>
                Phiên bản hiện tại chưa gửi OTP. Database chỉ lưu mã băm để đối chiếu và một email
                đã che bớt cho quản trị viên.
              </p>
            </div>
          </div>
        </div>

        {step === "EMAIL" ? (
          <form onSubmit={handleEmailSubmit} className="p-7 lg:p-9">
            <div className="max-w-xl">
              <p className="text-xs text-muted-foreground">Bước 1 trong 2</p>
              <h3 className="mt-2 font-serif text-2xl">Nhận diện người tham gia</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Nếu email đã từng tham gia, bạn sẽ vào bài ngay. Email mới sẽ cần bổ sung hồ sơ
                nghiên cứu một lần.
              </p>

              <div className="mt-8 space-y-2">
                <label htmlFor="participant-email" className="text-sm font-medium">Email</label>
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
                <p className="text-xs leading-5 text-muted-foreground">
                  Chưa có OTP nên email này là thông tin tự khai, chưa phải danh tính đã xác thực.
                </p>
              </div>

              {error && (
                <p className="mt-5 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive" role="alert">
                  {error}
                </p>
              )}

              <div className="mt-8 flex justify-end border-t border-border pt-6">
                <Button type="submit" size="lg" disabled={!emailReady || submitting} className="sm:min-w-48">
                  {submitting ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Đang kiểm tra</>
                  ) : (
                    <>Tiếp tục <ArrowRight className="h-4 w-4" /></>
                  )}
                </Button>
              </div>
            </div>
          </form>
        ) : (
          <form onSubmit={handleProfileSubmit} className="p-7 lg:p-9">
            <div className="max-w-xl">
              <p className="text-xs text-muted-foreground">Bước 2 trong 2</p>
              <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-serif text-2xl">Bổ sung hồ sơ nghiên cứu</h3>
                  <p className="mt-2 text-sm text-muted-foreground">{email.trim().toLowerCase()}</p>
                </div>
                <button
                  type="button"
                  onClick={() => { setStep("EMAIL"); setError(null); }}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <ArrowLeft className="h-3.5 w-3.5" /> Đổi email
                </button>
              </div>

              <div className="mt-7 space-y-2">
                <label htmlFor="participant-full-name" className="text-sm font-medium">
                  Họ và tên
                </label>
                <input
                  id="participant-full-name"
                  type="text"
                  autoComplete="name"
                  required
                  minLength={2}
                  maxLength={255}
                  autoFocus
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Ví dụ: Nguyễn Minh Anh"
                  className={fieldClassName}
                />
              </div>

              <div className="mt-6 grid gap-6 sm:grid-cols-[140px_1fr]">
                <div className="space-y-2">
                  <label htmlFor="participant-age" className="text-sm font-medium">Tuổi</label>
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
                  <label htmlFor="participant-occupation" className="text-sm font-medium">
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
                      <span className={`h-2 w-2 shrink-0 rounded-full ${gender === option.value ? "bg-background" : "border border-foreground/40"}`} />
                      {option.label}
                    </label>
                  ))}
                </div>
              </fieldset>

              {error && (
                <p className="mt-5 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive" role="alert">
                  {error}
                </p>
              )}

              <div className="mt-7 flex flex-col gap-3 border-t border-border pt-6 sm:flex-row sm:items-center sm:justify-between">
                <p className="max-w-xs text-xs leading-5 text-muted-foreground">
                  Tiếp tục đồng nghĩa với việc bạn đồng ý dùng câu trả lời cho mục đích thống kê nghiên cứu.
                </p>
                <Button type="submit" size="lg" disabled={!profileReady || submitting} className="shrink-0 sm:min-w-52">
                  {submitting ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Đang lưu thông tin</>
                  ) : (
                    <>Lưu và bắt đầu <ArrowRight className="h-4 w-4" /></>
                  )}
                </Button>
              </div>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
