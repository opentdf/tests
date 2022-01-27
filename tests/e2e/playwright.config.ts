import { PlaywrightTestConfig } from '@playwright/test';

const config: PlaywrightTestConfig = {
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: "http://localhost:3000",
    trace: 'on-first-retry',
    browserName: "chromium",
    headless: false,
    launchOptions: {
      slowMo: 50,
      devtools: true,
    }
  },
};

export default config;
