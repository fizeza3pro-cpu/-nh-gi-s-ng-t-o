import { defineConfig, mergeConfig } from "vite";
import baseConfig from "./vite.config";

// Cho phép các tên miền tunnel Pinggy; giữ proxy /api của cấu hình hiện tại.
export default mergeConfig(
  baseConfig,
  defineConfig({
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      allowedHosts: [".pinggy.link", ".pinggy-free.link"],
    },
  }),
);
