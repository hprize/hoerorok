import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 로컬 개발 시 /api 요청을 백엔드로 전달
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
