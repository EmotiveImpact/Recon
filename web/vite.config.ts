import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the site runs on Vite and asks Recon's own server
// (python3 -m recon.server) for everything under /api.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
