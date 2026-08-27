import { rm } from "node:fs/promises";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 이 머신에서 fs.rmSync(recursive)는 최상위 경로에 한글이 있으면 0xC0000409로
// 프로세스가 통째로 abort한다(메시지 없이 exit 127; 비동기 fs.promises.rm은 정상).
// vite의 emptyOutDir가 내부에서 rmSync를 쓰기 때문에 이 저장소("취업준비" 경로)의
// 빌드가 dist에 지울 게 있을 때마다 죽는다. 빌드 시작 전에 비동기 rm으로 outDir을
// 먼저 비워서 vite 쪽 rmSync가 호출될 일이 없게 한다.
const emptyOutDirAsync = {
  name: "empty-outdir-async",
  apply: "build",
  async configResolved(config) {
    await rm(resolve(config.root, config.build.outDir), { recursive: true, force: true });
  },
};

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
  plugins: [react(), emptyOutDirAsync],
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
