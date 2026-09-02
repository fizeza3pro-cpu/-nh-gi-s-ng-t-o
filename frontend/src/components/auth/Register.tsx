import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "./auth-context";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }

    setSubmitting(true);
    try {
      await register(username, password, fullName);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng ký thất bại.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen w-full relative bg-white">
      {/* Soft Dark Yellow Glow */}
      <div
        className="absolute inset-0 z-0"
        style={{
          backgroundImage: `
        radial-gradient(circle at center, #ccb755 0%, transparent 70%)
      `,
          opacity: 0.6,
          mixBlendMode: "multiply",
        }}
      />
      <div className="container flex min-h-[70vh] items-center justify-center py-16">
        <Card className="w-full max-w-sm animate-fade-in-up">
          <CardHeader className="text-center">
            <CardTitle>Tạo tài khoản</CardTitle>
            <CardDescription>Đăng ký để bắt đầu làm bài test.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="full_name" className="text-sm font-medium">
                  Họ tên
                </label>
                <input
                  id="full_name"
                  type="text"
                  autoFocus
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-inner focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="username" className="text-sm font-medium">
                  Tên đăng nhập
                </label>
                <input
                  id="username"
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-inner focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="password" className="text-sm font-medium">
                  Mật khẩu{" "}
                  <span className="text-muted-foreground">
                    (tối thiểu 8 ký tự)
                  </span>
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-inner focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? "Đang tạo tài khoản..." : "Đăng ký"}
              </Button>
            </form>

            <p className="mt-4 text-center text-sm text-muted-foreground">
              Đã có tài khoản?{" "}
              <Link
                to="/login"
                className="text-primary underline-offset-4 hover:underline"
              >
                Đăng nhập
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
