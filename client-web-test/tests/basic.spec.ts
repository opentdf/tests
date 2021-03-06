import { expect } from '@playwright/test';
import { authorize } from './helpers/operations';
import { test } from './helpers/fixtures';

test.describe('<TDF3JS/>', () => {
    test.beforeEach(async ({ page }) => {
        await authorize(page);
        await page.goto('/');
    });

    test('should use TDF3JS to encrypt/decrypt plain text', async ({ page }) => {
        const decryptedText = "Hello, world!";
        const header = page.locator('h2:has-text("Attributes")');
        await expect(header).toBeVisible();

        const encryptButton = await page.locator("#encrypt-button span");

        await expect(encryptButton).toBeVisible();
        await encryptButton.click();

        const decryptedMessage = await page.locator( `text=Text deciphered: ${decryptedText}`);
        await test.expect(decryptedMessage).toBeVisible();
    });
});
