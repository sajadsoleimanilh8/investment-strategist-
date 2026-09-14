/// <reference types="vitest/config" />
import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
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
