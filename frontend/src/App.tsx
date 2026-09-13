import { Navigate, Route, Routes } from "react-router-dom";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import Home from "@/pages/Home";
import Test from "@/pages/Test";
import Result from "@/pages/Result";
import AdminOverview from "@/pages/AdminOverview";
import AdminParticipants from "@/pages/AdminParticipants";
import AdminParticipantDetail from "@/pages/AdminParticipantDetail";
import AdminCodebooks from "@/pages/AdminCodebooks";
import Login from "./components/auth/Login";
import AdminRoute from "./components/auth/AdminRoute";

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
      </main>
    </div>
  );
}
