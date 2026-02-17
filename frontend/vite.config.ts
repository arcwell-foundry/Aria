import { defineConfig, type PluginOption } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig(async () => {
  const plugins: PluginOption[] = [react(), tailwindcss()];

  if (process.env.ANALYZE === "true") {
    const { visualizer } = await import("rollup-plugin-visualizer");
    plugins.push(
      visualizer({
        open: true,
        filename: "stats.html",
        gzipSize: true,
      }) as PluginOption,
    );
  }

  return {
    plugins,
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 3000,
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            "vendor-react": ["react", "react-dom", "react-router-dom"],
            "vendor-charts": ["recharts"],
            "vendor-motion": ["framer-motion"],
            "vendor-query": ["@tanstack/react-query"],
            "vendor-editor": [
              "@tiptap/react",
              "@tiptap/starter-kit",
              "@tiptap/extension-placeholder",
              "@tiptap/extension-underline",
            ],
            "vendor-video": ["@daily-co/daily-js", "@daily-co/daily-react"],
          },
        },
      },
    },
  };
});
