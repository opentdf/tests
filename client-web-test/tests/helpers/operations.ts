import {expect} from "@playwright/test";

export const authorize = async (page) => {
  await page.goto('/');
  const loginButton = await page.locator('[data-test-id=login-button]');

  await loginButton.click();

  await page.fill("#username", "user1");
  await page.fill("#password", "testuser123");
  await page.click("#kc-login");

  await page.waitForNavigation();
};
