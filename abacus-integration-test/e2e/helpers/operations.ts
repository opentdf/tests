import {APIRequestContext, expect, Page} from '@playwright/test'
import { selectors } from "./selectors";

export const authorize = async (page: Page) => {
  await page.goto('/');

  await Promise.all([
    page.waitForNavigation(),
    page.locator(selectors.loginButton).click()
  ]);

  await page.fill(selectors.loginScreen.usernameField, "user1");
  await page.fill(selectors.loginScreen.passwordField, "testuser123");
  await page.click(selectors.loginScreen.submitButton);

  await page.waitForSelector(selectors.logoutButton);
  // click the token message to close it and overcome potential overlapping problem
  await page.locator(selectors.tokenMessage).click()
};

export const createAuthority = async (page: Page, authority: any) => {
  await page.locator(selectors.attributesPage.newSectionBtn).click();
  await page.fill(selectors.attributesPage.newSection.authorityField, authority);
  await page.locator(selectors.attributesPage.newSection.submitAuthorityBtn).click();
};

export const createAttribute = async (page: Page, name: string, values: string[]) => {
  await page.fill(selectors.attributesPage.newSection.attributeNameField, name);
  for (let i = 0; i < values.length; i++) {
    const currentOrderField = `#order_${i}`
    await page.fill(currentOrderField, values[i]);
    await page.click(selectors.attributesPage.newSection.plusOrderButton)
  }
  await page.click(selectors.attributesPage.newSection.submitAttributeBtn);
}

export const assertAttributeCreatedMsg = async (page: Page) => {
  const attributeCreatedSuccessfullyMsg = await page.locator(selectors.alertMessage, {hasText: `Attribute created for`})
  await expect(attributeCreatedSuccessfullyMsg).toBeVisible();
  await attributeCreatedSuccessfullyMsg.click()
}

export const firstTableRowClick = async (table: string, page: Page) => {
  const firstRow = await page.locator(`[data-test-id=${table}] .ant-table-tbody>tr:first-child`);
  return await firstRow.click();
};

export const getLastPartOfUrl = async (page: Page) => {
  const url = page.url();
  return url.substring(url.lastIndexOf('/') + 1);
};

export const getAccessToken = async (page: Page) => {
  return await page.evaluate(() => {
    return sessionStorage.getItem("keycloak");
  });
};

export const deleteAttributeViaAPI = async (apiContext: APIRequestContext, authority: string, attrName: string, attrOrder: string[], attrRule = "hierarchy", attrState = "published") => {
  const deleteAttributeResponse = await apiContext.delete('http://localhost:65432/api/attributes/definitions/attributes', {
    data: {
      "authority": authority,
      "name": attrName,
      "rule": attrRule,
      "state": attrState,
      "order": attrOrder
    }
  })
  expect(deleteAttributeResponse.ok()).toBeTruthy()
};

export const deleteAuthorityViaAPI = async (apiContext: APIRequestContext, authority: string) => {
  const deleteAuthorityResponse = await apiContext?.delete('http://localhost:65432/api/attributes/authorities',{
    data: {
      "authority": authority
    },
  });
  console.log('deleteAuthorityResponse', deleteAuthorityResponse);
  // await expect(deleteAuthorityResponse?.status()).toBe(202)
  // await expect(deleteAuthorityResponse.ok()).toBeTruthy()
  return Promise.resolve();
};
