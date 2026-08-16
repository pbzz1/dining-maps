import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api/* to FastAPI so the browser sees a single origin
// while developing -- no CORS preflight, no absolute URLs scattered in the code.
// FastAPI's own routes live under /api too (see app/main.py), so this proxies
// the path unchanged rather than stripping the prefix -- dev and prod hit the
// exact same route strings, which is what a stripped prefix silently broke
// (worked in dev against the proxy, 404'd once deployed straight to the API).
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
      },
    },
  },
});
