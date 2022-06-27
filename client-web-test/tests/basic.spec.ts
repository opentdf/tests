import { expect } from '@playwright/test';
import { authorize } from './helpers/operations';
import { test } from './helpers/fixtures';
import fs from 'fs';

test.describe('<TDF3JS/>', () => {
    test.beforeEach(async ({ page }) => {
        await authorize(page);
        await page.goto('/');
    });

    test('should use FileClient to encrypt/decrypt file text', async ({ page }) => {
        const header = page.locator('h2:has-text("Attributes")');
        await expect(header).toBeVisible();
        const originalText = fs.readFileSync('./file.txt', 'utf8');
        throw originalText;
        // // @ts-ignore
        // const [ download ] = await Promise.all([
        //     page.waitForEvent('download'), // wait for download to start
        //     page.locator('id=username').setInputFiles("./file.txt")
        // ]);
        // // wait for download to complete
        // const path = await download.path();
        // const decryptedText = fs.readFileSync(path, 'utf8');
        //
        // expect(decryptedText).toEqual(originalText);
    });
});
