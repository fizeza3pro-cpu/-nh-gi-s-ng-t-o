import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

if (process.env.VERCEL && !/^https:\/\/.+\/api\/?$/.test(process.env.VITE_API_BASE_URL || "")) {
  throw new Error("Đặt VITE_API_BASE_URL=https://<backend>/api trong môi trường Vercel trước khi build.");
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "lottie-web": path.resolve(
        __dirname,
        "./node_modules/lottie-web/build/player/lottie_light.js",
      ),
    },
  },
  server: {
    allowedHosts: [".trycloudflare.com"],
    port: 5173,
    proxy: {
      "/api": process.env.AUT_API_PROXY || "http://localhost:8000",
    },
  },
});
