import { test, expect } from '@playwright/test';
import { selectors } from "./helpers/selectors";
import { authorize, firstTableRowClick, getLastPartOfUrl, login } from "./helpers/operations";

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

  // TODO: enable following logout-related tests after fixing PLAT-2299 (Logout operation is failed on CI with 'invalid redirect uri' error)
  test('should be able to log out on the Attributes page', async ({ page }) => {
    await test.step('Open Attributes route', async () => {
      await page.getByRole('link', { name: 'Attributes' }).click();
      await page.waitForURL('**/attributes');
    });

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

  test('should be able to log out on the Authorities page', async ({ page }) => {
    await test.step('Open Authorities route', async () => {
      await page.getByRole('link', { name: 'Authorities' }).click();
      await page.waitForURL('**/authorities');
    });

    // check that authority items are present when logged in
    await expect(page.locator(selectors.authoritiesPage.deleteAuthorityButton)).toBeVisible()

    await Promise.all([
      page.waitForNavigation(),
      page.click(selectors.logoutButton),
    ])
    await page.waitForSelector(selectors.loginButton);
    // check that authorities data isn't shown after log out
    const noDataInfo = page.locator(".ant-empty-description", {hasText: 'No Data'})
    await expect(noDataInfo).toBeVisible()
  });

  test('should be able to log out on the Entitlements page', async ({ page }) => {
    await test.step('Open Entitlements route', async () => {
      await page.getByRole('link', { name: 'Entitlements' }).click();
      await page.waitForURL('**/entitlements');
    });

    await Promise.all([
      page.waitForNavigation(),
      page.click(selectors.logoutButton),
    ])
    await page.waitForSelector(selectors.loginButton);

    // check that entities data isn't shown after log out - progress indicator is shown constantly
    const loadingDelay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
    await loadingDelay(3000)
    const progressIndicator = page.locator(".ant-spin-dot >> nth=0")
    await expect(progressIndicator).toBeVisible()
  });

  test('should be able to log out on the Entity Details page', async ({ page }) => {
    await test.step('Open Entitlements route', async () => {
      await page.getByRole('link', { name: 'Entitlements' }).click();
      await page.waitForURL('**/entitlements');
    });

    await Promise.all([
      page.waitForNavigation(),
      firstTableRowClick('users-table', page),
    ]);
    // check that entitlement items are present when logged in
    await expect(page.locator(selectors.entitlementsPage.entityDetailsPage.deleteEntitlementBtn)).toBeVisible()

    await Promise.all([
      page.waitForNavigation(),
      page.click(selectors.logoutButton),
    ])
    await page.waitForSelector(selectors.loginButton);
    // check that entitlement data isn't shown after log out
    const noDataInfo = page.locator(".ant-empty-description", {hasText: 'No Data'})
    await expect(noDataInfo).toBeVisible()
  });
});

test.describe('<Login/>', () => {
  test('succeeded on the Authorities page, actual data is loaded', async ({ page }) => {
    await authorize(page, "/authorities")

    await test.step('check that Authorities data is loaded', async () => {
      const authorityItems = await page.locator(selectors.authoritiesPage.authoritiesTableRow).all()
      const itemsQuantity = authorityItems.length
      await expect(itemsQuantity>0).toBeTruthy()
    })
  });

  test('succeeded on the Attributes page, actual data is loaded', async ({ page }) => {
    await authorize(page, "/attributes")

    await test.step('check that Attributes data is loaded', async () => {
      const attributeItems = await page.locator(selectors.attributesPage.attributeListItems).all()
      const itemsQuantity = attributeItems.length
      await expect(itemsQuantity>1).toBeTruthy()
    })
  });

  test('succeeded on the Entitlements page, actual data is loaded', async ({ page }) => {
    await authorize(page, "/entitlements")

    await test.step('check that Clients data is loaded', async () => {
      const clientsTableItems = await page.locator(`[data-test-id='clients-table'] .ant-table-row`).all();
      const clientsItemsQuantity = clientsTableItems.length
      await expect(clientsItemsQuantity>0).toBeTruthy()
    })

    await test.step('check that Users data is loaded', async () => {
      const usersTableItems = await page.locator(`[data-test-id='users-table'] .ant-table-row`).all();
      const usersItemsQuantity = usersTableItems.length
      await expect(usersItemsQuantity>0).toBeTruthy()
    })
  });

  // TODO: Uncomment after fixing the PLAT-2209 bug which leads to assertion failure
  test.skip('succeeded on the Entity Details page, actual data is loaded', async ({ page }) => {
    await authorize(page, "/entitlements")

    await Promise.all([
      page.waitForNavigation(),
      firstTableRowClick('users-table', page),
    ]);

    const entityId = await getLastPartOfUrl(page)

    await Promise.all([
      page.waitForNavigation(),
      page.click(selectors.logoutButton),
    ])

    await authorize(page, `/entitlements/users/${entityId}`)
    await expect(page.locator(selectors.entitlementsPage.entityDetailsPage.deleteEntitlementBtn)).toBeVisible()
  });

  test('is failed when using blank values', async ({ page }) => {
    await login(page, "", "")
    await expect(page.locator(selectors.loginScreen.errorMessage)).toBeVisible();
  });

  test('is failed when using wrong username', async ({ page }) => {
    await login(page, "non-existed-username", "testuser123")
    await expect(page.locator(selectors.loginScreen.errorMessage)).toBeVisible();
  });

  test('is failed when using wrong password', async ({ page }) => {
    await login(page, "user1", "wrong-password")
    await expect(page.locator(selectors.loginScreen.errorMessage)).toBeVisible();
  });
});
