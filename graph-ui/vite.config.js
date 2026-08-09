import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds the graph island to a single self-contained IIFE bundle (React included) that
// the vanilla index.html loads via <script src="/ui/assets/graph.js"> — no CDN, no ESM.
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "../server/src/static/assets",
    emptyOutDir: true,
    lib: {
      entry: "src/main.jsx",
      name: "NectarGraph",
      formats: ["iife"],
      fileName: () => "graph.js",
    },
    rollupOptions: {
      output: { assetFileNames: "graph.[ext]" },
    },
  },
});
