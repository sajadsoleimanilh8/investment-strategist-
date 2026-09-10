#!/usr/bin/env node
/**
 * Run the browser flow, or skip it — but never fail for the wrong reason.
 *
 * A CI box with no browser should not turn red because of it: that is a
 * missing capability, not a broken build, and a red that means "not installed"
 * teaches people to ignore reds. So this checks first and exits 0 with a
 * reason when it cannot run.
 *
 * Three things have to be true:
 *   1. @playwright/test is installed
 *   2. a browser exists — Playwright's own download, or a system Chrome/Edge
 *   3. Python can import the app, since Playwright starts the API itself
 *
 * `--strict` turns every skip into a failure, for a pipeline that *should*
 * have a browser and wants to know when it does not.
 */
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join } from "node:path";

//: The *local* runner, not `npx playwright`. npx will happily fetch a
//: standalone copy into its cache, and that copy cannot resolve
//: `@playwright/test` when it loads the config — a confusing
//: ERR_MODULE_NOT_FOUND that looks like a broken config file.
const RUNNER = join("node_modules", ".bin",
                    platform() === "win32" ? "playwright.cmd" : "playwright");

const strict = process.argv.includes("--strict");

function skip(reason) {
  console.log(`\n  SKIPPED: ${reason}`);
  console.log("  The browser flow did not run. Everything else is unaffected.");
  if (strict) {
    console.error("  --strict was set, so this is a failure.");
    process.exit(1);
  }
  process.exit(0);
}

// 1. the runner ------------------------------------------------------------
if (!existsSync(RUNNER)) {
  skip("@playwright/test is not installed (npm install -D @playwright/test)");
}

// 2. a browser -------------------------------------------------------------
function hasDownloadedBrowser() {
  const root = platform() === "win32"
    ? join(homedir(), "AppData", "Local", "ms-playwright")
    : platform() === "darwin"
      ? join(homedir(), "Library", "Caches", "ms-playwright")
      : join(homedir(), ".cache", "ms-playwright");
  if (!existsSync(root)) return false;
  // A directory alone is not enough: an interrupted download leaves the folder
  // behind without the executable, which is exactly how this machine failed.
  return readdirSync(root)
    .filter((entry) => entry.startsWith("chromium"))
    .some((entry) => {
      const dir = join(root, entry);
      return [
        join(dir, "chrome-win", "chrome.exe"),
        join(dir, "chrome-linux", "chrome"),
        join(dir, "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
      ].some(existsSync);
    });
}

const SYSTEM_BROWSERS = {
  chrome: [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
  ],
  msedge: [
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/microsoft-edge",
  ],
};

let channel = process.env.PLAYWRIGHT_CHANNEL ?? null;
if (!channel) {
  if (hasDownloadedBrowser()) {
    channel = "";                                   // Playwright's own build
  } else {
    for (const [name, paths] of Object.entries(SYSTEM_BROWSERS)) {
      if (paths.some(existsSync)) {
        channel = name;
        break;
      }
    }
  }
}

if (channel === null) {
  skip("no browser found — run `npx playwright install chromium`, or install "
     + "Chrome/Edge. On a restricted network the download may be blocked; a "
     + "system browser works just as well.");
}

// 3. the API the flow talks to --------------------------------------------
// No `shell: true` here: the shell would re-split `-c import app.main` into
// separate words and the probe would fail for a reason that has nothing to do
// with whether the API imports.
const python = spawnSync(
  process.env.PYTHON ?? "python",
  ["-c", "import app.main"],
  { cwd: "..", stdio: "ignore" },
);
if (python.status !== 0) {
  skip("the API is not importable — install the Python dependencies first "
     + "(pip install -r requirements.txt)");
}

// --- run it ---------------------------------------------------------------
console.log(channel
  ? `  Using the system browser: ${channel}`
  : "  Using Playwright's bundled Chromium");

const args = process.argv.slice(2).filter((arg) => arg !== "--strict");
const result = spawnSync(RUNNER, ["test", ...args], {
  stdio: "inherit",
  shell: platform() === "win32",
  env: { ...process.env, ...(channel ? { PLAYWRIGHT_CHANNEL: channel } : {}) },
});
process.exit(result.status ?? 1);
