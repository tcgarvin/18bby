// Vite config used only by shoot.py: same app as web/vite.config.ts, but the dev server's port and
// the API it proxies to come from the environment so the harness can use free ports.
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: fileURLToPath(new URL("../..", import.meta.url)),
  plugins: [react()],
  server: {
    port: Number(process.env.SHOT_WEB_PORT),
    strictPort: true,
    proxy: { "/api": `http://127.0.0.1:${process.env.SHOT_API_PORT}` },
  },
});
