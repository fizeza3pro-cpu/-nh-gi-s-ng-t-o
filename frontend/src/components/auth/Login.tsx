import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/components/auth/auth-context";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: Location })?.from?.pathname ?? "/";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen w-full bg-white relative">
      {/* Amber Glow Background */}
      <div
        className="absolute inset-0 z-0"
        style={{
          backgroundImage: `
        radial-gradient(125% 125% at 50% 90%, #ffffff 40%, #f59e0b 100%)
      `,
          backgroundSize: "100% 100%",
        }}
      />
      <div className="container flex min-h-[70vh] items-center justify-center py-16 relative z-10  ">
        <Card className="w-full max-w-sm animate-fade-in-up">
          <CardHeader>
            <CardTitle className="text-center">Đăng nhập</CardTitle>
            <CardDescription>
              Đăng nhập để làm bài test và xem lịch sử của bạn.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4 ">
              <div className="space-y-1.5">
                <label htmlFor="username" className="text-sm font-medium">
                  Tên đăng nhập
                </label>
                <input
                  id="username"
                  type="text"
                  required
                  autoFocus
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-inner focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="password" className="text-sm font-medium">
                  Mật khẩu
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-inner focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? "Đang đăng nhập..." : "Đăng nhập"}
              </Button>
            </form>

            <p className="mt-4 text-center text-sm text-muted-foreground">
              Chưa có tài khoản?{" "}
              <Link
                to="/register"
                className="text-primary underline-offset-4 hover:underline"
              >
                Đăng ký
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
