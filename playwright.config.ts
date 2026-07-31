import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  // Generated tests are per-run artifacts and are executed by path from the
  // harness. Keeping them out of the default suite stops one stale generated
  // file from turning the whole project red.
  testIgnore: '**/generated/**',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [
    ['list'],
    [
      'json',
      {
        // Kept configurable so concurrent runs cannot clobber each other's report.
        outputFile:
          process.env.REPLAYER_JSON_REPORT ?? 'artifacts/playwright-report.json',
      },
    ],
  ],
  use: {
    baseURL: process.env.REPLAYER_TARGET_URL ?? 'https://demo.playwright.dev/todomvc/',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
