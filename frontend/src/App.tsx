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
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <SiteHeader />
      <main className="flex-1">
        <Routes>
          {/* public router */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          {/* protected router */}
          <Route element={<RequireAuth />}>
            <Route path="/" element={<Home />} />
            <Route path="/test/:itemId" element={<Test />} />
            <Route path="/result/:responseId" element={<Result />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Route>
        </Routes>
      </main>
      <SiteFooter />
    </div>
  );
}
