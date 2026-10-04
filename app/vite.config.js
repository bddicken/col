import { readFileSync } from "node:fs";
import { defineConfig } from "vite";

// Serve the app's data files (data/processed/web, made by scripts/process.py)
// at "/". `vite build` copies them into dist/, which is what gets deployed.
// The social preview image (og.png) is not data, so the build adds it to dist/
// at a fixed path: link previews need an absolute, unhashed URL.
export default defineConfig({
  publicDir: "../data/processed/web",
  server: { port: 5173 },
  plugins: [
    {
      name: "og-image",
      generateBundle() {
        this.emitFile({ type: "asset", fileName: "og.png", source: readFileSync("og.png") });
      },
    },
  ],
});
