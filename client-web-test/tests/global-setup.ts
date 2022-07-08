import { chromium, FullConfig } from '@playwright/test';

export default async (config: FullConfig) => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.goto('http://localhost:65432');

    const loginButton = await page.locator('[data-test-id=login-button]');
    await loginButton.click();

    await page.fill("#username", "user1");
    await page.fill("#password", "testuser123");

    const signInButton = await page.locator('#kc-login');
    await signInButton.click();
    await page.context().storageState({ path: 'storageState.json' });
    await browser.close();
}
