import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В dev-режиме запросы к /api проксируются на backend (порт 8000), а /help — на сайт документации (npm run dev в папке docs, порт 5174).
// В продакшене тот же backend раздаёт и API, и собранный фронтенд — CORS не нужен.
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api": {
                target: process.env.VITE_API_PROXY ?? "http://localhost:8000",
                changeOrigin: true,
            },
            "/help": {
                target: process.env.VITE_DOCS_PROXY ?? "http://localhost:5174",
                changeOrigin: true,
                ws: true,
            },
        },
    },
});
