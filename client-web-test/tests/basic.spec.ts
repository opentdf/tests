import { expect } from '@playwright/test';
import { authorize } from './helpers/operations';
import { test } from './helpers/fixtures';
// @ts-ignore
import toString from 'stream-to-string';
import fs from 'fs';
import path from 'path';

const originalText = fs.readFileSync(path.join(__dirname, 'file.txt'), 'utf8');

test.describe('<TDF3JS/>', () => {
    test.beforeEach(async ({ page }) => {
        await authorize(page);
        await page.goto('/');
    });

    test('should use FileClient to encrypt/decrypt file text', async ({ page }) => {
        const header = page.locator('h2:has-text("Attributes")');
        await expect(header).toBeVisible();
        // @ts-ignore
        const [ download ] = await Promise.all([
            page.waitForEvent('download'), // wait for download to start
            page.locator("input[type=\"file\"]").setInputFiles("./file.txt")
        ]);
        // wait for download to complete
        const stream = await download.createReadStream();
        const decryptedText = await toString(stream);

        expect(decryptedText).toEqual(originalText);
    });
});
