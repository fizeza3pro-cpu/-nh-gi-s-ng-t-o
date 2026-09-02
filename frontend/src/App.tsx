import { Route, Routes } from "react-router-dom";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import Home from "@/pages/Home";
import Test from "@/pages/Test";
import Result from "@/pages/Result";
import Dashboard from "@/pages/Dashboard";
import Login from "./components/auth/Login";
import Register from "./components/auth/Register";
import RequireAuth from "./components/auth/RequireAuth";

export default function App() {
  function PublicLayout({ children }: { children: React.ReactNode }) {
    return (
      <div className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter />
      </div>
    );
  }
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <main className="flex-1">
        <Routes>
          {/* public router */}
          <Route
            path="/"
            element={
              <PublicLayout>
                <Home />
              </PublicLayout>
            }
          />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          {/* protected router */}
          <Route element={<RequireAuth />}>
            <Route path="/test/:itemId" element={<Test />} />
            <Route path="/result/:responseId" element={<Result />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Route>
        </Routes>
      </main>
    </div>
  );
}
