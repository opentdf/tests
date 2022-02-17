
export const authorize = async (page) => {
  await page.goto('http://localhost:3000/');
  const loginButton = page.locator('[data-test-id=login-button]');
  loginButton.click();

  await page.fill("#username", "entitlement-grantor");
  await page.fill("#password", "password");
  await page.click("#kc-login");

  await page.waitForNavigation();
  await page.waitForSelector('[data-test-id=logout-button]');
};

export const createAuthority = async (page, authority) => {
  const collapseHeader = page.locator('.ant-collapse-header');
  collapseHeader.click();
  page.fill('#authority', authority);
  await page.locator('#authority-submit').click();
};

export const firstTableRowClick = async (table, page) => {
  const firstRow = await page.locator(`[data-test-id=${table}] .ant-table-tbody>tr:first-child`);
  await firstRow.click();
};

export const getLastPartOfUrl = async (page) => {
  const url = page.url();
  return url.substring(url.lastIndexOf('/') + 1);
};
