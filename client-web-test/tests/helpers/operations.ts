export const authorize = async (page) => {
  await page.goto('/');
  const loginButton = page.locator('[data-test-id=login-button]');

  loginButton.click();

  await page.fill("#username", "user1");
  await page.fill("#password", "testuser123");
  await page.click("#kc-login");

  await page.waitForNavigation();
  await page.waitForSelector('[data-test-id=logout-button]');
};
