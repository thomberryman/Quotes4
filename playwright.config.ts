import { defineConfig } from "@playwright/test";

const reuseExistingServer = !process.env.CI;
const skipWebServer = process.env.PLAYWRIGHT_SKIP_WEBSERVER === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  webServer: skipWebServer
    ? undefined
    : [
        {
          command:
            `/bin/zsh -lc "source .venv/bin/activate && set -a && source .env && set +a && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 3001 --app-dir apps/api"`,
          url: "http://localhost:3001/api/v1/health",
          reuseExistingServer,
          timeout: 120_000,
        },
        {
          command:
            `/bin/zsh -lc "cd apps/web && NEXT_PUBLIC_API_BASE_URL=http://localhost:3001 npx next dev --hostname 127.0.0.1 --port 3000"`,
          url: "http://localhost:3000/login",
          reuseExistingServer,
          timeout: 120_000,
        },
      ],
});
