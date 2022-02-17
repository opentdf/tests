import { test, expect } from '@playwright/test';
import { authorize } from './helpers/operations';

test.describe('<App/>', () => {
  test.beforeEach(async ({ page }) => {
    await authorize(page);
  });

  test('renders initially', async ({ page }) => {
    const header = page.locator('h2', { hasText: "Attributes" });
    await expect(header).toBeVisible();
  });

  test('should get authorization token', async ({ page }) => {
    const loginButton = page.locator('[data-test-id=logout-button]');
    expect(loginButton).toBeTruthy();
  });
});
