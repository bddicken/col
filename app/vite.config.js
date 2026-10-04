import { defineConfig } from "vite";

// Serve the app's data files (data/processed/web, made by scripts/process.py)
// at "/". `vite build` copies them into dist/, which is what gets deployed.
export default defineConfig({
  publicDir: "../data/processed/web",
  server: { port: 5173 },
});
