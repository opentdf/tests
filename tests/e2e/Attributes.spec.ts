import { expect } from '@playwright/test';
import { authorize, createAuthority, firstTableRowClick } from './helpers/operations';
import { test } from './helpers/fixtures';

test.describe('<Attributes/>', () => {
  test.beforeEach(async ({ page, authority }) => {
    await authorize(page);
    await page.goto('/attributes');
    await createAuthority(page, authority);
  });

  test('renders initially', async ({ page }) => {
    const header = page.locator('h2', { hasText: "Attribute Rules" });
    await expect(header).toBeVisible();
  });

  test('should add authority', async ({ page, authority }) => {
    const newAuthority = await page.locator(`span:has-text("${authority}")`);
    test.expect(newAuthority).toBeTruthy();
  });

  test('should add attribute', async ({ page, attributeName, authority, attributeValue }) => {
    await page.click(`span:has-text("${authority}")`);
    await page.fill("#name", attributeName);
    await page.fill("#order_0", attributeValue);
    await page.click("#create-attribute-button");
  });

  test('assign attribute to client', async ({ page, authority, attributeName, attributeValue }) => {
    await page.goto("/entitlements");
    firstTableRowClick('clients-table', page);
    await page.waitForNavigation();

    await page.fill("#authority", authority);
    await page.fill("#name", attributeName);
    await page.fill("#value", attributeValue);
    await page.click("#assign-submit");

    await page.pause();
  });

  test.fixme('delete attribute', async ({ page, authority, attributeName, attributeValue }) => {
    await page.goto("/entitlements");
    firstTableRowClick('clients-table', page);
    await page.waitForNavigation();

    await page.fill("#authority", authority);
    await page.fill("#name", attributeName);
    await page.fill("#value", attributeValue);
    await page.click("#assign-submit");

    const tableVal = `${authority}/attr/${attributeName}/value/${attributeValue}`;

  });
});
