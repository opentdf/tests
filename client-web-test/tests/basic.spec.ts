import { expect } from '@playwright/test';
import { authorize } from './helpers/operations';
import { test } from './helpers/fixtures';
import toString from 'stream-to-string';
import fs from 'fs';
import path from 'path';

const acceptDownloads = true;
const originalText = fs.readFileSync(path.join(__dirname, 'file.txt'), 'utf8');

test.use({ acceptDownloads });

test.describe('<TDF3JS/>', () => {
    test.beforeEach(async ({ page }) => {
        await authorize(page);
        await page.goto('/');
    });

    test('should use TDF3JS to encrypt/decrypt plain text', async ({ page }) => {
        const header = await page.locator('h2:has-text("Attributes")');
        await expect(header).toBeVisible();
        await (page.locator("input[type=\"file\"]").setInputFiles(path.join(__dirname, 'file.txt')));
        const download = await page.waitForEvent('download');

        // wait for download to complete
        const stream = await download.createReadStream();
        const decryptedText = await toString(stream);

        expect(decryptedText).toEqual(originalText);
    });
});
