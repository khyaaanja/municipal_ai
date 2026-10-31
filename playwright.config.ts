import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.MUNICIPAL_AI_BASE_URL || 'http://localhost:8000';

export default defineConfig({
  testDir: './tests/ui',
  globalSetup: './tests/ui/global-setup.ts',

  // One worker on purpose. The app runs behind `manage.py runserver` (single
  // process) and the chat endpoints carry per-IP hourly quotas — parallel
  // workers turn a healthy app into a wall of 429s that read like failures.
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,

  // A real Groq answer is slow; these budgets are for the AI path, not the DOM.
  timeout: 90_000,
  expect: { timeout: 20_000 },

  reporter: [['list'], ['json', { outputFile: 'log/ui_results.json' }]],

  use: {
    baseURL: BASE_URL,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
