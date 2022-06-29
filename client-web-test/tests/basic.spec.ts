import { expect } from '@playwright/test';
import { authorize } from './helpers/operations';
import { test } from './helpers/fixtures';
// @ts-ignore
import toString from 'stream-to-string';
import fs from 'fs';
import path from 'path';

const originalText = fs.readFileSync(path.join(__dirname, 'file.txt'), 'utf8');

test.describe('<TDF3JS/>', () => {

    test('should use FileClient to encrypt/decrypt file text', async ({ browser }) => {
        const context = await browser.newContext({ acceptDownloads: true });
        const page = await context.newPage();
        await authorize(page);
        await page.goto('/');

        const header = page.locator('h2:has-text("Attributes")');
        await expect(header).toBeVisible();
        await page.locator("input[type=\"111file\"]").setInputFiles(path.join(__dirname, 'file.txt'));
        // @ts-ignore
        const download = await page.waitForEvent('download'); // wait for download to start
        // wait for download to complete
        const stream = await download.createReadStream();
        const decryptedText = await toString(stream);

        expect(decryptedText).toEqual(originalText);
    });
});
