import {APIRequestContext, expect, Page} from '@playwright/test';
import {
  createAuthority,
  firstTableRowClick,
  getLastPartOfUrl,
  authorize,
  deleteAuthorityViaAPI,
  getAccessToken,
  assertAttributeCreatedMsg,
  createAttribute,
  removeAllAttributesOfAuthority
} from './helpers/operations';
import { test } from './helpers/fixtures';
import {selectors} from "./helpers/selectors";

let authToken: string | null;
let apiContext: APIRequestContext;
const { randomUUID } = require('crypto');

const createNewEntitlement = async (page: Page, authority: string, attributeName: string, attributeValue: string) => {
  await page.fill(selectors.entitlementsPage.authorityNamespaceField, authority);
  await page.keyboard.press('Enter')
  await page.fill(selectors.entitlementsPage.attributeNameField, attributeName);
  await page.fill(selectors.entitlementsPage.attributeValueField, attributeValue);
  await page.click(selectors.entitlementsPage.submitAttributeButton);
}

test.describe('<Entitlements/>', () => {
  test.beforeEach(async ({ page , playwright, authority}) => {
    await authorize(page);
    authToken = await getAccessToken(page)

    await page.getByRole('link', { name: 'Attributes' }).click();
    await page.waitForURL('**/attributes');

    await createAuthority(page, authority);
    // click success message to close it and overcome potential overlapping problem
    const authorityCreatedMsg = page.locator(selectors.alertMessage, {hasText:'Authority was created'})
    await authorityCreatedMsg.click()

    await page.getByRole('link', { name: 'Entitlements' }).click();
    await page.waitForURL('**/entitlements');

    apiContext = await playwright.request.newContext({
      extraHTTPHeaders: {
        'Authorization': `Bearer ${authToken}`,
      },
    });
  });

  test.afterEach(async ({ authority, page}, testInfo) => {
    if (testInfo.status !== testInfo.expectedStatus) {
      let screenshotPath = `test-results/screenshots/screenshot-${randomUUID()}.png`;
      await page.screenshot({ path: screenshotPath, fullPage: true });
      testInfo.annotations.push({ type: 'testrail_attachment', description: screenshotPath });
    }

    await removeAllAttributesOfAuthority(apiContext, authority);
    await deleteAuthorityViaAPI(apiContext, authority)
  })

  test.afterAll(async ({ }) => {
    await apiContext.dispose();
  });

  test('Page is rendered properly, entities tables are shown', async ({ page }) => {
    const clientTableHeader = page.locator('b', { hasText: "Clients table" });
    await expect(clientTableHeader).toBeVisible();

    const tableHeader = page.locator('b', { hasText: "Users table" });
    await expect(tableHeader).toBeVisible();
  });

  test('User/PE Details page is opened by click on a user table row', async ({ page }, testInfo) => {
    await Promise.all([
        page.waitForNavigation(),
        firstTableRowClick('users-table', page),
    ]);

    const id = getLastPartOfUrl(page);
    const header = page.locator(selectors.secondaryHeader, { hasText: `User ${id}` });
    test.expect(header).toBeTruthy();
  });

  test('Client/NPE Details page is opened by click on a client table row', async ({ page }) => {
    await Promise.all([
        page.waitForNavigation(),
        firstTableRowClick('clients-table', page),
    ]);

    const id = getLastPartOfUrl(page);
    const header = page.locator(selectors.secondaryHeader, { hasText: `Client ${id}` });
    test.expect(header).toBeTruthy();
  });

  test('Able to assign new entitlement to entity when using valid existing values', async ({ page , authority, attributeName, attributeValue}) => {
    await test.step('Create attribute', async () => {
      await page.getByRole('link', { name: 'Attributes' }).click();
      await page.waitForURL('**/attributes');
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    });

    await test.step('Open Entitlements route', async () => {
      await page.getByRole('link', { name: 'Entitlements' }).click();
      await page.waitForURL('**/entitlements');
    });

    await Promise.all([
        page.waitForNavigation(),
        firstTableRowClick('clients-table', page),
    ]);

    await test.step('Entitle attribute', async() => {
      await createNewEntitlement(page, authority, attributeName, attributeValue)
    })

    await test.step('Assert result message', async() => {
      const successfulEntitlementMsg = await page.locator(selectors.alertMessage, {hasText: "Entitlement updated!"})
      await expect(successfulEntitlementMsg).toBeVisible()
    })

    await test.step('Input fields are properly cleared after successful submission', async() => {
      await expect(page.locator(selectors.entitlementsPage.authorityNamespaceField)).toHaveText("")
      await expect(page.locator(selectors.entitlementsPage.attributeNameField)).toHaveText("")
      await expect(page.locator(selectors.entitlementsPage.attributeValueField)).toHaveText("")
    })
  });

  test('Able to delete existed entity entitlement', async ({ page, authority, attributeName, attributeValue}) => {
    const tableValue = `${authority}/attr/${attributeName}/value/${attributeValue}`

    await test.step('Open Attributes route', async () => {
      await page.getByRole('link', { name: 'Attributes' }).click();
      await page.waitForURL('**/attributes');
    });

    await test.step('Create an attribute and assert creation', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Open Entitlements route', async () => {
      await page.getByRole('link', { name: 'Entitlements' }).click();
      await page.waitForURL('**/entitlements');
    });

    await test.step('Open table', async () => {
      await firstTableRowClick('clients-table', page)
    });

    await test.step('Create a new entitlement', async () => {
      await createNewEntitlement(page, authority, attributeName, attributeValue)

      const successfulEntitlementMsg = await page.locator(selectors.alertMessage, {hasText: "Entitlement updated!"})
      await successfulEntitlementMsg.click()
      await expect(page.locator(selectors.entitlementsPage.entityDetailsPage.tableRow, {hasText: tableValue})).toBeVisible()
    });

    await test.step('Click on table cell', async () => {
      await page.click(selectors.entitlementsPage.entityDetailsPage.tableCell)
      await page.waitForSelector(selectors.entitlementsPage.entityDetailsPage.tableRow)
    });

    const originalTableRows = await page.locator(selectors.entitlementsPage.entityDetailsPage.tableRow).all()
    const originalTableSize = originalTableRows.length

    const entityId = await getLastPartOfUrl(page)
    const deleteButtonForAddedEntitlement = await page.getByRole('row', { name: `${tableValue} ${entityId} Delete` }).getByRole('button', { name: 'Delete' });

    await test.step('Be able to cancel entitlement removal', async() => {
      await deleteButtonForAddedEntitlement.click()
      await page.click(selectors.entitlementsPage.entityDetailsPage.confirmDeletionModal.cancelDeletionBtn);
    })

    await test.step('Delete single item', async () => {
      await deleteButtonForAddedEntitlement.click()
      await page.click(selectors.entitlementsPage.entityDetailsPage.confirmDeletionModal.confirmDeletionBtn);
    });

    await test.step('Click on table cell', async () => {
      await page.click(selectors.entitlementsPage.entityDetailsPage.tableCell)
      await page.waitForSelector(selectors.entitlementsPage.entityDetailsPage.tableRow)
    });

    await test.step('Assert success message', async () => {
      const entitlementDeletedMsg = await page.locator(selectors.alertMessage, {hasText: `Entitlement ${tableValue} deleted`})
      await expect(entitlementDeletedMsg).toBeVisible()
      await entitlementDeletedMsg.click()
    });

    await test.step('Match table rows after deletion', async () => {
      await page.waitForSelector(selectors.entitlementsPage.entityDetailsPage.tableRow)
      const updatedTableRows = await page.locator(selectors.entitlementsPage.entityDetailsPage.tableRow).all();
      const updatedTableSize = updatedTableRows.length;
      expect(updatedTableSize === (originalTableSize - 1)).toBeTruthy()
    });
  });
});
