import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the dashboard talks to the API on :8000 through this proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.PGMLENS_API_URL ?? "http://localhost:8000" },
  },
  build: { sourcemap: true },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
