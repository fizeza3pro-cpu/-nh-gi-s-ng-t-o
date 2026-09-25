import { Navigate, Route, Routes } from "react-router-dom";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import Home from "@/pages/Home";
import Test from "@/pages/Test";
import Result from "@/pages/Result";
import History from "@/pages/History";
import AdminOverview from "@/pages/AdminOverview";
import AdminParticipants from "@/pages/AdminParticipants";
import AdminParticipantDetail from "@/pages/AdminParticipantDetail";
import AdminCodebooks from "@/pages/AdminCodebooks";
import Login from "./components/auth/Login";
import AdminRoute from "./components/auth/AdminRoute";

function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="fixed left-4 top-4 z-[70] -translate-y-24 rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-transform focus:translate-y-0"
      >
        Đi tới nội dung chính
      </a>
      <SiteHeader />
      <main id="main-content" tabIndex={-1} className="flex-1 outline-none">
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
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
          <Route path="/admin/login" element={<Login />} />
          <Route path="/login" element={<Navigate to="/admin/login" replace />} />

          <Route
            path="/test/:itemId"
            element={
              <PublicLayout>
                <Test />
              </PublicLayout>
            }
          />
          <Route
            path="/result/:responseId"
            element={
              <PublicLayout>
                <Result />
              </PublicLayout>
            }
          />
          <Route
            path="/history"
            element={
              <PublicLayout>
                <History />
              </PublicLayout>
            }
          />

          <Route path="/dashboard" element={<Navigate to="/admin" replace />} />

          {/* admin — giao diện TÁCH BIỆT hoàn toàn, sidebar riêng, không dùng SiteHeader/Footer */}
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminOverview />} />
            <Route path="/admin/participants" element={<AdminParticipants />} />
            <Route path="/admin/participants/:participantId" element={<AdminParticipantDetail />} />
            <Route path="/admin/codebooks" element={<AdminCodebooks />} />
            <Route path="/admin/codebooks/:itemId" element={<AdminCodebooks />} />
          </Route>
      </Routes>
    </div>
  );
}
