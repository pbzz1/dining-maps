import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api/* to FastAPI so the browser sees a single origin
// while developing -- no CORS preflight, no absolute URLs scattered in the code.
// In production the built files are served from a static host and do talk to the
// API cross-origin, which is why FastAPI still needs CORSMiddleware (app/main.py).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
