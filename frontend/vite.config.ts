import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";
import path from "node:path";

// The site reads a published snapshot produced by the Python pipeline.
// `npm run build` -> normal static site (Vercel). `npm run build:artifact`
// -> one self-contained HTML file.
export default defineConfig(({ mode }) => ({
  plugins: [react(), ...(mode === "artifact" ? [viteSingleFile()] : [])],
  resolve: { alias: { "@snapshot": path.resolve(__dirname, "../data/snapshots/latest.json") } },
  build: { outDir: mode === "artifact" ? "dist-artifact" : "dist", chunkSizeWarningLimit: 2000 },
  test: { environment: "node" },
}));
