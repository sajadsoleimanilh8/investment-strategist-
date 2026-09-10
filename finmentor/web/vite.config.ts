/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: {
    environment: "jsdom",
    // jsdom serves "about:blank" by default, which is an opaque origin — and
    // an opaque origin has no localStorage. The app stores its refresh token
    // there, so the tests need a real one.
    environmentOptions: { jsdom: { url: "http://localhost:5173" } },
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
