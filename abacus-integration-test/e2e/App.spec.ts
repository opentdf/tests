import { test, expect } from '@playwright/test';
import { selectors } from "./helpers/selectors";
import { authorize } from "./helpers/operations";

test.describe('<App/>', () => {
  test.beforeEach(async ({ page }) => {
    await authorize(page);
    await page.goto('/');
  });

  test('renders initially', async ({ page }) => {
    const header = page.locator('h2', { hasText: "Attributes" });
    await expect(header).toBeVisible();
  });

  test('should get authorization token', async ({ page }) => {
    const logoutButton = page.locator(selectors.logoutButton);
    expect(logoutButton).toBeTruthy();
  });

  // TODO: enable back after switching to usage of the latest Frontend chart during CI test run (PLAT-2146 task) since issue appears in old hardcoded version (using Keycloak <v.18)
  test.skip('should be able to log out', async ({ page }) => {
    await page.goto('/attributes');
    await Promise.all([
      page.waitForNavigation(),
      page.click(selectors.logoutButton),
    ])
    await page.waitForSelector(selectors.loginButton);
    // check that data isn't shown
    const authorityDropdown = page.locator(".ant-select-selector >> nth=1")
    await authorityDropdown.click()
    await expect(page.locator('.ant-empty-description')).toHaveText('No Data')
  });
});
