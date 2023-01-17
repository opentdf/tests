import { APIRequestContext, expect, Locator } from '@playwright/test';
import {
  createAuthority,
  createAttribute,
  assertAttributeCreatedMsg,
  firstTableRowClick,
  authorize,
  getAccessToken,
  deleteAttributeViaAPI,
  deleteAuthorityViaAPI
} from './helpers/operations';
import { test } from './helpers/fixtures';
import { selectors } from "./helpers/selectors";

test.describe('<Attributes/>', () => {
  const existedOrderValue = '.ant-tabs-tab-btn >> nth=0'
  let authToken: string | null;
  let apiContext: APIRequestContext;
  let authorityCreatedMsg: Locator;

  test.beforeEach(async ({ page, playwright, authority }) => {
    await authorize(page);
    authToken = await getAccessToken(page);

    await page.getByRole('link', { name: 'Attributes' }).click();
    await page.waitForURL('**/attributes');

    await createAuthority(page, authority);
    // click success message to close it and overcome potential overlapping problem
    authorityCreatedMsg = page.locator(selectors.alertMessage, {hasText:'Authority was created'})
    await authorityCreatedMsg.click()

    apiContext = await playwright.request.newContext({
      extraHTTPHeaders: {
        'Authorization': `Bearer ${authToken}`,
      },
    });
  });

  test.afterEach(async ({ authority}) => {
    await deleteAuthorityViaAPI(apiContext, authority)
  })

  test.afterAll(async ({ }) => {
    await apiContext.dispose();
  });

  test('renders initially', async ({ page }) => {
    const header = page.locator('h2', { hasText: "Attribute Rules" });
    await expect(header).toBeVisible();
  });

  test('should add authority', async ({ page, authority }) => {
    const newAuthority = await page.locator(`span:has-text("${authority}")`);
    expect(newAuthority).toBeTruthy();
  });

  test('should add attribute, should filter attributes by Name, Order, Rule', async ({ page, attributeName, authority, attributeValue }) => {
    await createAttribute(page, attributeName, [attributeValue])
    await assertAttributeCreatedMsg(page)

    const attributesHeader = selectors.attributesPage.attributesHeader;
    const filterModal = attributesHeader.filterModal;

    await test.step('Filter by existed Name', async () => {
      await page.click(attributesHeader.filtersToolbarButton)
      await page.fill(filterModal.nameInputField, attributeName)
      await page.click(filterModal.submitBtn)
      await page.click(attributesHeader.itemsQuantityIndicator)
      const filteredAttributesListByName = await page.$$(selectors.attributesPage.attributeItem)
      expect(filteredAttributesListByName.length).toBe(1)
    })

    await test.step('Filter by non-existed Name', async () => {
      await page.click(attributesHeader.filtersToolbarButton)
      await page.click(filterModal.clearBtn)
      await page.fill(filterModal.nameInputField, 'invalidAttributeName')
      await page.click(filterModal.submitBtn)
      await expect(page.locator(attributesHeader.itemsQuantityIndicator)).toHaveText('Total 0 items')
    })

    await test.step('Filter by Order', async () => {
      await page.click(filterModal.clearBtn)
      await page.fill(filterModal.orderInputField, attributeValue)
      await page.click(filterModal.submitBtn)
      await page.click(attributesHeader.itemsQuantityIndicator)
      await page.waitForSelector(selectors.attributesPage.attributeItem);
      const filteredAttributesListByOrder = await page.$$(selectors.attributesPage.attributeItem)
      expect(filteredAttributesListByOrder.length).toBe(1)
    })

    await test.step('Filter by Rule', async () => {
      await page.click(attributesHeader.filtersToolbarButton)
      await page.click(filterModal.clearBtn)
      await page.fill(filterModal.ruleInputField, 'allOf')
      await page.click(filterModal.submitBtn)
      await expect(page.locator(attributesHeader.itemsQuantityIndicator)).toHaveText('Total 0 items')
      await page.fill(filterModal.ruleInputField, 'hierarchy')
      await page.click(filterModal.submitBtn)
      await expect(page.locator(attributesHeader.itemsQuantityIndicator)).toHaveText('Total 1 items')
      await page.click(attributesHeader.itemsQuantityIndicator)
      const filteredAttributesListByRule = await page.$$(selectors.attributesPage.attributeItem)
      expect(filteredAttributesListByRule.length).toBe(1)
    })

    await test.step('Cleanup', async () => {
      await deleteAttributeViaAPI(apiContext, authority, attributeName,[attributeValue])
    })
  });

  test('should not be able to create the attribute with already existed name for the same authority', async ({ page,authority,attributeName, attributeValue }) => {
    await test.step('Create an attribute', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Try to create another attribute with the same name', async() => {
      await createAttribute(page, attributeName, ["Custom"])
    })

    await test.step('Assert failure message', async() => {
      const attributeCreationFailedMessage = await page.locator(selectors.alertMessage, {hasText: `Request failed`})
      await expect(attributeCreationFailedMessage).toBeVisible()
    })

    await test.step('Cleanup', async () => {
      await deleteAttributeViaAPI(apiContext, authority, attributeName,[attributeValue])
    })
  });

  test('should be able to create an attribute with already used name for another authority', async ({ page,authority,attributeName, attributeValue }) => {
    await test.step('Create an attribute', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Create another authority', async() => {
      await page.fill(selectors.attributesPage.newSection.authorityField, `${authority}2`);
      await page.locator(selectors.attributesPage.newSection.submitAuthorityBtn).click();
      await authorityCreatedMsg.click()
    })

    await test.step('Create an attribute with the same name for another authority', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Cleanup', async () => {
      await deleteAttributeViaAPI(apiContext, `${authority}2`, attributeName,[attributeValue])
      await deleteAttributeViaAPI(apiContext, authority, attributeName,[attributeValue])
      await deleteAuthorityViaAPI(apiContext, `${authority}2`)
    })
  });

  test('should sort attributes by Name, ID, rule, values_array', async ({ page, authority}) => {
    const ascendingSortingOption = page.locator('.ant-cascader-menu-item-content', {hasText: 'ASC'})
    const descendingSortingOption = page.locator('.ant-cascader-menu-item-content', {hasText: 'DES'})
    const nameSortingSubOption = page.locator('.ant-cascader-menu-item-content', {hasText: 'name'})
    const ruleSortingSubOption = page.locator('.ant-cascader-menu-item-content', {hasText: 'rule'})
    const idSortingSubOption = page.locator('.ant-cascader-menu-item-content', {hasText: 'id'})
    const valuesSortingSubOption = page.locator('.ant-cascader-menu-item-content', {hasText: 'values_array'})
    const sortByToolbarButton = selectors.attributesPage.attributesHeader.sortByToolbarButton
    const firstAttributeName = '1st attribute'
    const secondAttributeName = 'Z 2nd attribute'
    const thirdAttributeName = '3rd attribute'

    const createAttributeViaAPI = async (attrName: string, attrRule: string, attrOrder: string[]) => {
      const createAttributeResponse = await apiContext.post('http://localhost:65432/api/attributes/definitions/attributes', {
        data: {
          "authority": authority,
          "name": attrName,
          "rule": attrRule,
          "state": "published",
          "order": attrOrder
        }
      })
      expect(createAttributeResponse.ok()).toBeTruthy()
    }

    const assertItemsOrderAfterSorting = async (expectedFirstItemName: string, expectedSecondItemName: string, expectedLastItemName: string) => {
      const firstItemNameAfterSorting = await page.innerText(".ant-col h3 >> nth=0")
      expect(firstItemNameAfterSorting == expectedFirstItemName).toBeTruthy()
      const secondItemNameAfterSorting = await page.innerText(".ant-col h3 >> nth=1")
      expect(secondItemNameAfterSorting == expectedSecondItemName).toBeTruthy()
      const lastItemNameAfterSorting = await page.innerText('.ant-col h3 >> nth=-1')
      expect(lastItemNameAfterSorting == expectedLastItemName).toBeTruthy()
    }

    await test.step('Data setup', async () => {
      await createAttributeViaAPI(firstAttributeName, 'anyOf', ['A', 'G', 'H'])
      await createAttributeViaAPI(secondAttributeName, 'allOf', ['C', 'G', 'H'])
      await createAttributeViaAPI(thirdAttributeName, 'hierarchy', ['B', 'G', 'H'])
    })

    await test.step('Open page with correspondent data', async () => {
      // reload page to renew data
      await page.getByRole('link', { name: 'Entitlements' }).click();
      await page.waitForURL('**/entitlements');

      await page.getByRole('link', { name: 'Attributes' }).click();
      await page.waitForURL('**/attributes');

      // select proper authority
      await page.click('[data-test="select-authorities-button"]', {force: true})
      await page.locator('.ant-select-item-option-content', { hasText: authority }).click();

      await expect(page.locator('.ant-select-selection-item >> nth=1')).toHaveText(authority)
      await expect(page.locator(selectors.attributesPage.attributesHeader.itemsQuantityIndicator)).toHaveText('Total 3 items')
    })

    await test.step('Sort by Name ASC', async () => {
      await page.click(sortByToolbarButton)
      await ascendingSortingOption.click()
      await nameSortingSubOption.click()
      await assertItemsOrderAfterSorting(firstAttributeName, thirdAttributeName, secondAttributeName)
    })

    await test.step('Sort by Name DESC', async () => {
      await page.click(sortByToolbarButton, {force: true})
      await descendingSortingOption.click()
      await nameSortingSubOption.click()
      await assertItemsOrderAfterSorting(secondAttributeName, thirdAttributeName, firstAttributeName)
    })

    await test.step('Sort by Rule ASC', async () => {
      await page.click(sortByToolbarButton, {force: true})
      await ascendingSortingOption.click()
      await ruleSortingSubOption.click()
      await assertItemsOrderAfterSorting(secondAttributeName, firstAttributeName, thirdAttributeName)
    })

    await test.step('Sort by Rule DESC', async () => {
      await page.click(sortByToolbarButton, {force: true})
      await descendingSortingOption.click()
      await ruleSortingSubOption.click()
      await assertItemsOrderAfterSorting(thirdAttributeName, firstAttributeName, secondAttributeName)
    })

    await test.step('Sort by ID ASC', async () => {
      await page.click(sortByToolbarButton, {force: true})
      await ascendingSortingOption.click()
      await idSortingSubOption.click()
      await assertItemsOrderAfterSorting(firstAttributeName, secondAttributeName, thirdAttributeName)
    })

    await test.step('Sort by ID DESC', async () => {
      await page.click(sortByToolbarButton, {force: true})
      await descendingSortingOption.click()
      await idSortingSubOption.click()
      await assertItemsOrderAfterSorting(thirdAttributeName, secondAttributeName, firstAttributeName)
    })

    await test.step('Sort by Order values ASC', async () => {
      await page.click(sortByToolbarButton, {force: true})
      await ascendingSortingOption.click()
      await valuesSortingSubOption.click()
      await assertItemsOrderAfterSorting(firstAttributeName, thirdAttributeName, secondAttributeName)
    })

    await test.step('Sort by Order values DESC', async () => {
      await page.click(sortByToolbarButton, {force: true})
      await descendingSortingOption.click()
      await valuesSortingSubOption.click()
      await assertItemsOrderAfterSorting(secondAttributeName, thirdAttributeName, firstAttributeName)
    })

    await test.step('Cleanup', async () => {
      await deleteAttributeViaAPI(apiContext, authority, firstAttributeName,['A', 'G', 'H'], "anyOf")
      await deleteAttributeViaAPI(apiContext, authority, secondAttributeName,['C', 'G', 'H'], "allOf")
      await deleteAttributeViaAPI(apiContext, authority, thirdAttributeName,['B', 'G', 'H'], "hierarchy")
    })
  });

  test('should delete attribute entitlement', async ({ page, authority, attributeName, attributeValue }) => {
    await page.getByRole('link', { name: 'Entitlements' }).click();
    await page.waitForURL('**/entitlements');

    await Promise.all([
      page.waitForNavigation(),
      firstTableRowClick('clients-table', page),
    ]);

    await page.click(selectors.entitlementsPage.entityDetailsPage.tableCell)
    await page.waitForSelector(selectors.entitlementsPage.entityDetailsPage.tableRow)
    const originalTableRows = await page.$$(selectors.entitlementsPage.entityDetailsPage.tableRow)
    const originalTableSize = originalTableRows.length

    // Delete single item
    await page.locator(selectors.entitlementsPage.entityDetailsPage.deleteEntitlementBtn).click();
    await page.locator(selectors.entitlementsPage.entityDetailsPage.deleteEntitlementModalBtn).click();

    await page.click(selectors.entitlementsPage.entityDetailsPage.tableCell)
    await page.waitForSelector(selectors.entitlementsPage.entityDetailsPage.tableRow)
    const updatedTableRows = await page.$$(selectors.entitlementsPage.entityDetailsPage.tableRow)
    const updatedTableSize = updatedTableRows.length

    expect(updatedTableSize === (originalTableSize - 1)).toBeTruthy()
  });

  test('should edit attribute rule', async ({ page , authority, attributeName, attributeValue}) => {
    const restrictiveAccessDropdownOption = page.locator('.ant-select-item-option', {hasText:'Restrictive Access'})
    const ruleUpdatedMsg = page.locator(selectors.alertMessage, {hasText: `Rule was updated!`})
    const attributeDetailsSection = selectors.attributesPage.attributeDetailsSection

    await test.step('Create an attribute and assert creation', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await page.click(selectors.attributesPage.attributesHeader.itemsQuantityIndicator)
    await page.click(selectors.attributesPage.newSectionBtn);

    await test.step('Update rule and check result', async() => {
      await page.click(existedOrderValue)
      await page.click(attributeDetailsSection.editRuleButton)
      await page.click(attributeDetailsSection.ruleDropdown)
      await restrictiveAccessDropdownOption.click()
      await page.click(attributeDetailsSection.saveRuleButton)
      await expect(ruleUpdatedMsg).toBeVisible()
    })

    await test.step('Cleanup', async () => {
      await deleteAttributeViaAPI(apiContext, authority, attributeName,[attributeValue], "allOf")
    })
  });

  test('should create an attribute with multiple order values, able to edit order of values, able to cancel editing', async ({ page , authority, attributeName, attributeValue}) => {
    const ruleUpdatedMsg = page.locator(selectors.alertMessage, {hasText: `Rule was updated!`})

    await test.step('Create an attribute with multiple Order values and check result message', async() => {
      await createAttribute(page, attributeName, [`${attributeValue}1`, `${attributeValue}2`, `${attributeValue}3`, `${attributeValue}4`])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Open the Details section', async() => {
      await page.click(selectors.attributesPage.attributesHeader.itemsQuantityIndicator)
      await page.locator(selectors.attributesPage.newSectionBtn).click();
      await page.waitForSelector('.ant-tabs-tab-btn');
      await page.locator('.ant-tabs-tab-btn', { hasText: `${attributeValue}1` }).click();

      await expect(page.locator('.ant-tabs-tab-btn', { hasText: `${attributeValue}1` })).toHaveAttribute('aria-selected', 'true')
    })

    await test.step('Should be able to close the Details section', async() => {
      await page.click(selectors.attributesPage.attributeDetailsSection.closeDetailsSectionButton)
      await expect(page.locator('.ant-tabs-tab-btn', { hasText: `${attributeValue}1` })).toHaveAttribute('aria-selected', 'false')
    })

    await test.step('Reopen the Details section and enter editing mode', async() => {
      await page.locator('.ant-tabs-tab-btn', { hasText: `${attributeValue}1` }).click();
      await page.locator(selectors.attributesPage.attributeDetailsSection.editRuleButton).click()
    })

    await test.step('Should be able to cancel attribute editing', async() => {
      await page.click(selectors.attributesPage.attributeDetailsSection.cancelRuleSavingButton)
    })

    await test.step('Reenter editing mode and edit order of values items using drag-and-drop feature', async() => {
      await page.locator(selectors.attributesPage.attributeDetailsSection.editRuleButton).click()
      const firstOrderItemInEditableList = '.order-list__item >> nth=0'
      const fourthOrderItemInEditableList = '.order-list__item >> nth=3'
      await page.dragAndDrop(fourthOrderItemInEditableList, firstOrderItemInEditableList )
      await page.click(selectors.attributesPage.attributeDetailsSection.saveRuleButton)
      await expect(ruleUpdatedMsg).toBeVisible()
      const updatedFirstOrderValue = page.locator('.ant-tabs-tab-btn >> nth=0')
      await expect(updatedFirstOrderValue).toHaveText(`${attributeValue}4`)
    })

    await test.step('Cleanup', async () => {
      await deleteAttributeViaAPI(apiContext, authority, attributeName,[`${attributeValue}4`, `${attributeValue}2`, `${attributeValue}3`, `${attributeValue}1`])
    })
  });

  test('Should delete consequent Order field using the Minus icon', async ({ page , attributeName, attributeValue}) => {
    let orderFieldsQuantityAfterAdding: number
    await page.fill(selectors.attributesPage.newSection.attributeNameField, attributeName);
    await page.fill(selectors.attributesPage.newSection.orderField1, attributeValue);

    await test.step('Consequent Order field is properly added', async () => {
      await page.click(selectors.attributesPage.newSection.plusOrderButton)
      const orderFieldsAfterAdding = await page.$$('label[title="Order"]')
      orderFieldsQuantityAfterAdding = orderFieldsAfterAdding.length
    })

    await test.step('Order field is properly removed', async () => {
      await page.click(selectors.attributesPage.newSection.minusOrderButton)
      const orderFieldsAfterRemoval = await page.$$('label[title="Order"]')
      const orderFieldsQuantityAfterRemoval = orderFieldsAfterRemoval.length
      expect(orderFieldsQuantityAfterRemoval === (orderFieldsQuantityAfterAdding - 1)).toBeTruthy()
    })

    await test.step('Order field value is properly dropped after removal and re-adding', async () => {
      await page.click(selectors.attributesPage.newSection.plusOrderButton)
      await expect(page.locator(selectors.attributesPage.newSection.orderField1)).toBeEmpty()
      const secondOrderField = await page.locator('#order_1')
      await expect(secondOrderField).toBeEmpty()
    })
  });

  test('should show empty state of the Entitlements table in the Attribute Details section when there are no entitlements', async ({page, authority, attributeName,attributeValue}) => {
    await createAttribute(page, attributeName, [attributeValue])
    await assertAttributeCreatedMsg(page)
    await page.click(selectors.attributesPage.attributesHeader.itemsQuantityIndicator)
    await page.locator(selectors.attributesPage.newSectionBtn).click();
    const existedOrderValue = page.locator('.ant-tabs-tab-btn >> nth=0')
    await existedOrderValue.click()
    await expect(page.locator('#entitlements-table .ant-empty-description')).toHaveText('No Data')

    await test.step('Cleanup', async () => {
      await deleteAttributeViaAPI(apiContext, authority, attributeName,[attributeValue])
    })
  });

  test('should show existed entitlements in the Attribute Details section', async ({ page, authority,attributeName, attributeValue }) => {
    await test.step('Create an attribute', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Switch to the Entitlements page', async() => {
      await page.getByRole('link', { name: 'Entitlements' }).click();
      await page.waitForURL('**/entitlements');
      await Promise.all([
        page.waitForNavigation(),
        firstTableRowClick('clients-table', page),
      ])
    })

    await test.step('Entitle the attribute', async() => {
      await page.click(selectors.entitlementsPage.authorityNamespaceField)

      await page.waitForSelector('.ant-select-item-option-content')
      await page.locator('.ant-select-item-option-content', { hasText: authority }).click({ force: true });

      await page.fill(selectors.entitlementsPage.attributeNameField, attributeName);
      await page.fill(selectors.entitlementsPage.attributeValueField, attributeValue);
      await page.click(selectors.entitlementsPage.submitAttributeButton);
    })

    await test.step('Switch to the Attributes page and select proper authority', async() => {
      await page.getByRole('link', { name: 'Attributes' }).click();
      await page.waitForURL('**/attributes');

      await page.click(selectors.attributesPage.attributesHeader.authorityDropdownButton, { force:true })

      await page.waitForSelector('.ant-select-item-option-content')
      await page.locator('.ant-select-item-option-content', { hasText: authority }).click({ force: true });
    })

    await test.step('Open the Details section and verify presence of the entitled item in the table', async() => {
      const existedOrderValue = page.locator('.ant-tabs-tab-btn >> nth=0')
      await existedOrderValue.click()
      const tableEntitlements = await page.$$("#entitlements-table .ant-table-tbody")
      expect(tableEntitlements.length).toBe(1)
      const tableValue = `${authority}/attr/${attributeName}/value/${attributeValue}`
      await expect(page.locator('.ant-table-cell', {hasText: tableValue})).toBeVisible()
    })

    await test.step('Cleanup', async () => {
      await deleteAttributeViaAPI(apiContext, authority, attributeName,[attributeValue])
    })
  });

  test('should be able to delete an attribute', async ({ page,authority,attributeName, attributeValue }) => {
    await test.step('Create an attribute', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Open the Details section', async() => {
      await page.click(selectors.attributesPage.attributesHeader.itemsQuantityIndicator)
      await page.locator(selectors.attributesPage.newSectionBtn).click();
      const orderValue = '.ant-tabs-tab-btn >> nth=-1'
      await page.click(orderValue)
    })

    await test.step('Be able to cancel attribute removal', async() => {
      await page.locator(selectors.attributesPage.attributeDetailsSection.deleteAttributeButton).click()
      await page.locator(selectors.attributesPage.attributeDetailsSection.confirmAttributeDeletionModal.cancelDeletionBtn).click()
    })

    await test.step('Delete attribute', async() => {
      await page.locator(selectors.attributesPage.attributeDetailsSection.deleteAttributeButton).click()
      await page.locator(selectors.attributesPage.attributeDetailsSection.confirmAttributeDeletionModal.confirmDeletionBtn).click()
    })

    await test.step('Assert success message', async() => {
      const successfulDeletionMsg = await page.locator(selectors.alertMessage, {hasText: `Attribute ${attributeName} deleted`})
      await expect(successfulDeletionMsg).toBeVisible()
    })
  });
});
