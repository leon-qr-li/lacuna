import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));

// `npm run dev` proxies the API to a backend started with `python -m lacuna_app ... --port 8765`.
// Two pages: the app (index.html) and the admin site (admin.html, served only on admin.<domain>).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: { input: { main: resolve(here, "index.html"), admin: resolve(here, "admin.html") } },
  },
});
