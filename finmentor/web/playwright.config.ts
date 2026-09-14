import { defineConfig, devices } from "@playwright/test";

/**
 * One browser flow, against the real thing.
 *
 * Playwright starts both servers itself, so `npm run test:e2e` needs nothing
 * running beforehand — the API in DEMO_MODE against the dev database, and the
 * Vite dev server in front of it.
 *
 * `channel: "chrome"` uses the Chrome already installed on the machine rather
 * than Playwright's own download. That download is blocked on this network,
 * and a test that cannot run is worth less than one that uses the browser
 * already there. `scripts/e2e.mjs` picks a channel that exists and skips the
 * whole run when none does.
 */
const API_PORT = 8123;
const WEB_PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  // The flow is a single ordered story: signing up, then onboarding, then
  // reading the dashboard. Running it in parallel would mean three users.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [["list"]],
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    channel: process.env.PLAYWRIGHT_CHANNEL ?? "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  webServer: [
    {
      // DEMO_MODE and no scheduler: no external API is contacted, and the
      // market cache is served from whatever the seed left behind.
      command:
        `python -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT} --log-level warning`,
      cwd: "..",
      url: `http://127.0.0.1:${API_PORT}/healthz`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        DEMO_MODE: "true",
        ENABLE_SCHEDULER: "false",
        // Same reasoning as DEMO_MODE: no external API on a path this suite
        // depends on being deterministic (app/market/live.py's poll loop).
        MARKET_LIVE_SOURCE: "off",
        // The model is deliberately unreachable, not faked. The fake provider
        // would let the Ask flow pass while proving nothing about what a user
        // sees when Ollama is down — which is the Phase 5 guarantee this suite
        // is here to check.
        LOCAL_LLM_PROVIDER: "ollama",
        OLLAMA_HOST: "http://127.0.0.1:1",
        REMOTE_LLM_ENABLED: "false",
        AUTH_RATE_LIMIT_PER_MINUTE: "0",
        ASK_RATE_LIMIT_PER_MINUTE: "0",
        CORS_ORIGINS: `["http://127.0.0.1:${WEB_PORT}","http://localhost:${WEB_PORT}"]`,
      },
    },
    {
      // `--host 127.0.0.1` is not optional: Vite otherwise binds "localhost",
      // which resolves to ::1 first on Windows, and Playwright polls IPv4 —
      // so the server is up and the wait times out anyway.
      command:
        `npm run dev -- --port ${WEB_PORT} --strictPort --host 127.0.0.1`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { VITE_API_BASE_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
