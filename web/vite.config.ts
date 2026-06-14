/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// MIDAS web bundle.
// - Built assets land in the wheel at src/midas/flagship/dashboard/static/app.
// - `base` matches the FastAPI mount point (/static/app/) so all imports resolve under loopback.
// - Dev server proxies /api, /events, /login, /static, and / to the local FastAPI.
// - `manifest: true` lets the Python side discover hashed entry filenames if needed later.
export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: path.resolve(__dirname, "../src/midas/flagship/dashboard/static/app"),
    emptyOutDir: true,
    manifest: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        // Stable file names → straightforward cache + CSP allow-list under `'self'`.
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/events": { target: "http://127.0.0.1:8765", changeOrigin: true, ws: false },
      "/login": "http://127.0.0.1:8765",
      "/snapshot": "http://127.0.0.1:8765",
      "/outcomes": "http://127.0.0.1:8765",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
