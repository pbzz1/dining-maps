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
// index.html 의 %SITE_URL% (og:image/og:url 절대 URL). 배포 스크립트가 넘기고, 로컬은 빈값.
process.env.SITE_URL ??= "";

export default defineConfig({
  plugins: [react()],
  envPrefix: ["VITE_", "SITE_URL"],
  server: {
    port: Number(process.env.PORT) || 5173, // PORT는 워크트리 등 5173이 점유된 환경용

    proxy: {
      "/api": {
        // API_PORT는 워크트리 등 8000이 본 체크아웃의 서버에 점유된 환경용
        target: `http://127.0.0.1:${process.env.API_PORT || 8000}`,
        changeOrigin: true,
      },
    },
  },
});
