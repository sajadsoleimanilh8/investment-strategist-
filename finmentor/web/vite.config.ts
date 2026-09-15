/// <reference types="vitest/config" />
import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The dev server fronts the API, so the browser sees one origin — which
    // is how this app deploys (FastAPI serving the built SPA) and what the
    // OAuth handoff cookie needs: `SameSite=Lax` is not sent on a cross-site
    // request, so a split-origin dev setup can start a provider sign-in and
    // never finish one.
    //
    // Setting VITE_API_BASE_URL opts out and talks to the API directly, which
    // is what the Playwright suite does; everything except the OAuth exchange
    // works that way.
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        ws: true,                       // the live-price socket goes through too
      },
      "/healthz": process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
    },
  },
  test: {
    // `e2e/` is Playwright's, and its `test.describe` is not vitest's — left
    // in, vitest collects those files and fails on the import rather than on
    // anything real. The two suites run from different commands on purpose.
    exclude: [...configDefaults.exclude, "e2e/**"],
    environment: "jsdom",
    // jsdom serves "about:blank" by default, which is an opaque origin — and
    // an opaque origin has no localStorage. The app stores its refresh token
    // there, so the tests need a real one.
    environmentOptions: { jsdom: { url: "http://localhost:5173" } },
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
