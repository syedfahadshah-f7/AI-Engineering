import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the Vite dev server proxies /api to FastAPI, so the browser
// only ever talks to its own origin and never holds the OpenRouter key.
export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1000 }, // three.js is one large chunk
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
