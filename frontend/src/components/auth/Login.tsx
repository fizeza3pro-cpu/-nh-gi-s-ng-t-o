import { useState, type FormEvent } from "react";
import { ArrowLeft, Database, Layers3, Loader2, ShieldCheck } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/components/auth/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const ADMIN_CAPABILITIES = [
  {
    icon: Database,
    title: "Theo dõi dữ liệu khảo sát",
    body: "Quan sát tiến độ thu thập và trạng thái từng lượt trả lời.",
  },
  {
    icon: Layers3,
    title: "Kiểm tra sổ mã",
    body: "Đọc căn cứ phân loại và lịch sử đối chiếu của hệ thống.",
  },
  {
    icon: ShieldCheck,
    title: "Khu vực được bảo vệ",
    body: "Chỉ tài khoản quản trị mới có quyền truy cập.",
  },
] as const;

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: Location })?.from?.pathname ?? "/admin";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Không thể đăng nhập. Hãy kiểm tra lại thông tin.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-[minmax(0,0.92fr)_minmax(32rem,1.08fr)]">
      <section className="relative overflow-hidden bg-foreground px-6 py-8 text-background sm:px-10 lg:flex lg:min-h-screen lg:flex-col lg:justify-between lg:px-14 lg:py-12">
        <div className="pointer-events-none absolute inset-0 grid-paper opacity-[0.06]" aria-hidden="true" />
        <div className="relative">
          <Link
            to="/"
            className="inline-flex items-center gap-2 rounded-md text-sm text-background/65 transition-colors hover:text-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-background/60"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Về trang khảo sát
          </Link>

          <div className="mt-12 flex items-center gap-3 lg:mt-20">
            <span className="grid h-11 w-11 place-items-center rounded-lg border border-background/25 font-serif text-sm font-semibold">
              AUT
            </span>
            <div>
              <p className="font-serif text-lg">Bàn quản trị nghiên cứu</p>
              <p className="text-xs text-background/55">Alternative Uses Test</p>
            </div>
          </div>

          <h1 className="mt-10 max-w-xl text-balance font-serif text-4xl leading-tight sm:text-5xl">
            Một nơi để đọc tiến độ, kiểm tra căn cứ và bảo toàn dữ liệu nghiên cứu.
          </h1>
        </div>

        <div className="relative mt-12 grid gap-px overflow-hidden rounded-xl border border-background/15 bg-background/15 sm:grid-cols-3 lg:grid-cols-1">
          {ADMIN_CAPABILITIES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="bg-foreground/95 p-5 lg:flex lg:gap-4">
              <Icon className="h-5 w-5 shrink-0 text-research-bright" aria-hidden="true" />
              <div className="mt-3 lg:mt-0">
                <p className="text-sm font-medium">{title}</p>
                <p className="mt-1 text-xs leading-5 text-background/55">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="flex items-center justify-center px-6 py-14 sm:px-10 lg:px-16">
        <div className="w-full max-w-md">
          <p className="font-mono text-xs text-research">AUT / ADMIN</p>
          <h2 className="mt-4 text-balance font-serif text-4xl tracking-tight">
            Đăng nhập quản trị
          </h2>
          <p className="mt-3 text-pretty text-sm leading-6 text-muted-foreground">
            Dùng tài khoản quản trị được cấp để mở bảng theo dõi nghiên cứu.
          </p>

          <form
            onSubmit={handleSubmit}
            className="mt-9 space-y-6"
            aria-busy={submitting}
          >
            <div className="space-y-2">
              <label htmlFor="username" className="text-sm font-medium">
                Tên đăng nhập
              </label>
              <Input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                spellCheck={false}
                required
                autoFocus
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Nhập tên đăng nhập…"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium">
                Mật khẩu
              </label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Nhập mật khẩu…"
              />
            </div>

            {error ? (
              <p
                role="alert"
                className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm leading-6 text-destructive"
              >
                {error} Hãy thử lại hoặc liên hệ người phụ trách hệ thống.
              </p>
            ) : null}

            <Button type="submit" size="lg" className="w-full" disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Đăng nhập…
                </>
              ) : (
                "Đăng nhập"
              )}
            </Button>
          </form>

          <p className="mt-8 border-t border-border pt-5 text-xs leading-5 text-muted-foreground">
            Phiên đăng nhập chỉ dùng cho nghiệp vụ quản trị. Người tham gia khảo sát không cần tài khoản.
          </p>
        </div>
      </section>
    </main>
  );
}
