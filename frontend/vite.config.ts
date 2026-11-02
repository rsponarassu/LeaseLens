import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"

/**
 * LeaseLens web client.
 *
 * In development the Vite server proxies `/api` to the FastAPI app so the
 * browser sees a single origin: no CORS preflights, and relative URLs keep
 * working in production when FastAPI serves the built bundle itself.
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const target = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000"

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      port: Number(env.PORT || 5173),
      strictPort: false,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          // Analysis can take a while on a scanned PDF with OCR enabled.
          timeout: 180_000,
        },
      },
    },
    preview: {
      port: Number(env.PORT || 4173),
    },
    build: {
      outDir: "dist",
      sourcemap: mode === "development",
      chunkSizeWarningLimit: 900,
    },
  }
})
