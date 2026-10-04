import { defineConfig } from "vite";

// Serve the pipeline output (data/processed) as static files at "/".
export default defineConfig({
  publicDir: "../data/processed",
  server: { port: 5173 },
});
