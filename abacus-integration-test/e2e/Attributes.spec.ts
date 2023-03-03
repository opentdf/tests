import { APIRequestContext, expect, Locator } from '@playwright/test';
import {
  createAuthority,
  createAttribute,
  assertAttributeCreatedMsg,
  firstTableRowClick,
  authorize,
  getAccessToken,
  deleteAuthorityViaAPI,
  createAttributeViaAPI,
  removeAllAttributesOfAuthority,
  getLastPartOfUrl
} from './helpers/operations';
import { test } from './helpers/fixtures';
import { selectors } from "./helpers/selectors";

test.describe('<Attributes/>', () => {
  let authToken: string | null;
  let apiContext: APIRequestContext;
  let authorityCreatedMsg: Locator;
  const attributeDetailsSection = selectors.attributesPage.attributeDetailsSection

  test.beforeEach(async ({ page, playwright, authority }) => {
    await authorize(page);
    authToken = await getAccessToken(page);

    await page.getByRole('link', { name: 'Attributes' }).click();
    await page.waitForURL('**/attributes');

    await createAuthority(page, authority);
    // click success message to close it and overcome potential overlapping problem
    authorityCreatedMsg = await page.locator(selectors.alertMessage, {hasText:'Authority was created'});
    await authorityCreatedMsg.click();

    apiContext = await playwright.request.newContext({
      extraHTTPHeaders: {
        'Authorization': `Bearer ${authToken}`,
      },
    });
  });

  test.afterEach(async ({ authority}, testInfo) => {
    await removeAllAttributesOfAuthority(apiContext, authority);
    await deleteAuthorityViaAPI(apiContext, authority)
    if (testInfo.title == 'should be able to create an attribute with already used name for another authority') {
      await removeAllAttributesOfAuthority(apiContext, `${authority}2`);
      await deleteAuthorityViaAPI(apiContext, `${authority}2`)
    }
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

  test('should not be able to create authority with empty name or name of non-url format', async ({ page }) => {
    await test.step('creation is failed when using blank name', async () => {
      await page.click(selectors.attributesPage.newSection.submitAuthorityBtn)
      const authorityWarningMessage = page.locator('.ant-form-item-explain-error', {hasText: '\'authority\' is required'})
      await expect(authorityWarningMessage).toBeVisible()
    })

    await test.step('creation is failed when using name of invalid non-url format', async () => {
      await page.fill(selectors.attributesPage.newSection.authorityField, 'invalidAuthorityNameFormat');
      await page.locator(selectors.attributesPage.newSection.submitAuthorityBtn).click();
      const authorityCreationFailedMessage = await page.locator(selectors.alertMessage, {hasText: `Authority was not created`})
      await expect(authorityCreationFailedMessage).toBeVisible()
    })
  });

  test('should add attribute, should filter attributes by Name, Order, Rule', async ({ page, attributeName, attributeValue }) => {
    const attributesHeader = selectors.attributesPage.attributesHeader;
    const filterModal = attributesHeader.filterModal;

    await test.step('Create attribute', async () => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Filter by existed Name', async () => {
      await page.click(attributesHeader.filtersToolbarButton);
      await page.fill(filterModal.nameInputField, attributeName);
      await page.click(filterModal.submitBtn);
      await page.click(attributesHeader.itemsQuantityIndicator);

      const filteredAttributesListByName = await page.locator(selectors.attributesPage.attributeItem).all();
      expect(filteredAttributesListByName.length).toBe(1)
    })

    await test.step('Filter by non-existed Name', async () => {
      await page.click(attributesHeader.filtersToolbarButton);
      await page.click(filterModal.clearBtn);
      await page.fill(filterModal.nameInputField, 'invalidAttributeName');
      await page.click(filterModal.submitBtn);
      await expect(page.locator(attributesHeader.itemsQuantityIndicator)).toHaveText('Total 0 items')
    })

    await test.step('Filter by Order', async () => {
      await page.click(filterModal.clearBtn);
      await page.fill(filterModal.orderInputField, attributeValue);
      await page.click(filterModal.submitBtn);
      await page.click(attributesHeader.itemsQuantityIndicator);
      await page.waitForSelector(selectors.attributesPage.attributeItem);
      const filteredAttributesListByOrder = await page.locator(selectors.attributesPage.attributeItem).all();
      expect(filteredAttributesListByOrder.length).toBe(1)
    })

    await test.step('Filter by Rule', async () => {
      await page.click(attributesHeader.filtersToolbarButton);
      await page.click(filterModal.clearBtn, { force: true });
      await page.fill(filterModal.ruleInputField, 'allOf');
      await page.click(filterModal.submitBtn);
      await expect(page.locator(attributesHeader.itemsQuantityIndicator)).toHaveText('Total 0 items')
      await page.fill(filterModal.ruleInputField, 'hierarchy')
      await page.click(filterModal.submitBtn)
      await expect(page.locator(attributesHeader.itemsQuantityIndicator)).toHaveText('Total 1 items')
      await page.click(attributesHeader.itemsQuantityIndicator)
      const filteredAttributesListByRule = await page.locator(selectors.attributesPage.attributeItem).all();
      expect(filteredAttributesListByRule.length).toBe(1)
    })
  });

  test('should not be able to create the attribute with already existed name for the same authority', async ({ page,attributeName, attributeValue }) => {
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
  });

  test('attribute creation is blocked when not filling required Name and Order values', async ({ page}) => {
    await test.step('creation is failed when using blank Name', async () => {
      await page.fill(selectors.attributesPage.newSection.orderField1, 'fillOrder');
      await page.click(selectors.attributesPage.newSection.submitAttributeBtn)
      const emptyNameWarningMessage = page.locator('.ant-form-item-explain-error', {hasText: 'Please input name value!'})
      await expect(emptyNameWarningMessage).toBeVisible()
    })

    await test.step('creation is failed when using blank Order value', async () => {
      await page.fill(selectors.attributesPage.newSection.attributeNameField, 'fillName');
      await page.fill(selectors.attributesPage.newSection.orderField1, '');
      await page.click(selectors.attributesPage.newSection.submitAttributeBtn)
      const emptyOrderWarningMessage = page.locator('.ant-form-item-explain-error', {hasText: 'Please input order value!'})
      await expect(emptyOrderWarningMessage).toBeVisible()
    })
  });

  test('should be able to create an attribute with already used name for another authority', async ({ page,authority,attributeName, attributeValue }) => {
    await test.step('Create an attribute', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Create another authority', async () => {
      await page.fill(selectors.attributesPage.newSection.authorityField, `${authority}2`);
      await page.locator(selectors.attributesPage.newSection.submitAuthorityBtn).click();
      await authorityCreatedMsg.click()
    })

    await test.step('Create an attribute with the same name for another authority', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })
  });

  test('should sort attributes by Name, rule, ID and Order values', async ({ page, authority}) => {
    const sortByToolbarButton = selectors.attributesPage.attributesHeader.sortByToolbarButton;
    const firstAttributeName = '1st attribute';
    const secondAttributeName = 'Z 2nd attribute';
    const thirdAttributeName = '3rd attribute';

    const assertItemsOrderAfterSorting = async (expectedFirstItemName: string, expectedSecondItemName: string, expectedLastItemName: string) => {
      const firstItemNameAfterSorting = await page.innerText(".ant-col h3 >> nth=0")
      expect(firstItemNameAfterSorting == expectedFirstItemName).toBeTruthy()
      const secondItemNameAfterSorting = await page.innerText(".ant-col h3 >> nth=1")
      expect(secondItemNameAfterSorting == expectedSecondItemName).toBeTruthy()
      const lastItemNameAfterSorting = await page.innerText('.ant-col h3 >> nth=-1')
      expect(lastItemNameAfterSorting == expectedLastItemName).toBeTruthy()
    }

    await test.step('Data setup', async () => {
      await createAttributeViaAPI(apiContext, authority, firstAttributeName, ['A', 'G', 'H'], 'anyOf');
      await createAttributeViaAPI(apiContext, authority, secondAttributeName, ['C', 'G', 'H'], 'allOf');
      await createAttributeViaAPI(apiContext, authority, thirdAttributeName, ['B', 'G', 'H'], 'hierarchy');
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
      await page.locator(sortByToolbarButton).click({ force: true })
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'ASC'}).click()
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'name'}).click()
      await assertItemsOrderAfterSorting(firstAttributeName, thirdAttributeName, secondAttributeName)
    })

    await test.step('Sort by Name DESC', async () => {
      await page.locator(sortByToolbarButton).click({ force: true })
      await page.waitForSelector('.ant-cascader-menu-item-content')
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'DES'}).click()
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'name'}).click()
      await assertItemsOrderAfterSorting(secondAttributeName, thirdAttributeName, firstAttributeName)
    })

    await test.step('Sort by Rule ASC', async () => {
      await page.locator(sortByToolbarButton).click({ force: true })
      await page.waitForSelector('.ant-cascader-menu-item-content')
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'ASC'}).click()
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'rule'}).click()
      await assertItemsOrderAfterSorting(secondAttributeName, firstAttributeName, thirdAttributeName)
    })

    await test.step('Sort by Rule DESC', async () => {
      await page.locator(sortByToolbarButton).click({ force: true })
      await page.waitForSelector('.ant-cascader-menu-item-content')
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'DES'}).click()
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'rule'}).click()
      await assertItemsOrderAfterSorting(thirdAttributeName, firstAttributeName, secondAttributeName)
    })

    await test.step('Sort by ID ASC', async () => {
      await page.locator(sortByToolbarButton).click({ force: true })
      await page.waitForSelector('.ant-cascader-menu-item-content')
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'ASC'}).click()
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'id'}).click()
      await assertItemsOrderAfterSorting(firstAttributeName, secondAttributeName, thirdAttributeName)
    })

    await test.step('Sort by ID DESC', async () => {
      await page.waitForSelector('#sort-by-button')
      await page.locator(sortByToolbarButton).click({ force: true });
      await page.waitForSelector('.ant-cascader-menu-item-content')
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'DES'}).click()
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'id'}).click()
      await assertItemsOrderAfterSorting(thirdAttributeName, secondAttributeName, firstAttributeName)
    })

    await test.step('Sort by Order values ASC', async () => {
      await page.locator(sortByToolbarButton).click({ force: true });
      await page.waitForSelector('.ant-cascader-menu-item-content')
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'ASC'}).click()
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'values_array'}).click()
      await assertItemsOrderAfterSorting(firstAttributeName, thirdAttributeName, secondAttributeName)
    })

    await test.step('Sort by Order values DESC', async () => {
      await page.locator(sortByToolbarButton).click({ force: true });
      await page.waitForSelector('.ant-cascader-menu-item-content')
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'DES'}).click()
      await page.locator('.ant-cascader-menu-item-content', {hasText: 'values_array'}).click()
      await assertItemsOrderAfterSorting(secondAttributeName, thirdAttributeName, firstAttributeName)
    })
  });

  test('should delete attribute entitlement', async ({ page, authority, attributeName, attributeValue}) => {
    const tableValue = `${authority}/attr/${attributeName}/value/${attributeValue}`

    await test.step('Create an attribute and assert creation', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await test.step('Open entitlements route', async () => {
      await page.getByRole('link', { name: 'Entitlements' }).click();
      await page.waitForURL('**/entitlements');
    });

    await test.step('Open table', async () => {
      await Promise.all([
        page.waitForNavigation(),
        firstTableRowClick('clients-table', page),
      ]);
    });

    await test.step('Create a new entitlement', async () => {
      await page.type(selectors.entitlementsPage.authorityNamespaceField, authority);
      await page.keyboard.press('Enter')
      await page.fill(selectors.entitlementsPage.attributeNameField, attributeName);
      await page.fill(selectors.entitlementsPage.attributeValueField, attributeValue);
      await page.click(selectors.entitlementsPage.submitAttributeButton);

      const successfulEntitlementMsg = await page.locator(selectors.alertMessage, {hasText: "Entitlement updated!"})
      await successfulEntitlementMsg.click()
      await expect(page.locator(selectors.entitlementsPage.entityDetailsPage.tableRow, {hasText: tableValue})).toBeVisible()
    });

    await test.step('Click on table cell', async () => {
      await page.click(selectors.entitlementsPage.entityDetailsPage.tableCell)
      await page.waitForSelector(selectors.entitlementsPage.entityDetailsPage.tableRow)
    });

    const originalTableRows = await page.locator(selectors.entitlementsPage.entityDetailsPage.tableRow).all();
    const originalTableSize = originalTableRows.length;

    const entityId = await getLastPartOfUrl(page)
    const deleteButtonForAddedEntitlement = await page.getByRole('row', { name: `${tableValue} ${entityId} Delete` }).getByRole('button', { name: 'Delete' });

    await test.step('Be able to cancel entitlement removal', async() => {
      await deleteButtonForAddedEntitlement.click()
      await page.click(selectors.entitlementsPage.entityDetailsPage.confirmDeletionModal.cancelDeletionBtn);
    })

    await test.step('Delete single item', async () => {
      await deleteButtonForAddedEntitlement.click();
      await page.locator(selectors.entitlementsPage.entityDetailsPage.confirmDeletionModal.confirmDeletionBtn).click();
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

  test('should edit attribute rule, non applied changes are discarded after cancellation', async ({ page , attributeName, attributeValue}) => {
    const restrictiveAccessDropdownOption = page.locator('.ant-select-item-option', {hasText:'Restrictive Access'})
    const ruleUpdatedMsg = page.locator(selectors.alertMessage, {hasText: `Rule was updated!`})
    const attributeDetailsSection = selectors.attributesPage.attributeDetailsSection

    await test.step('Create an attribute and assert creation', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await page.click(selectors.attributesPage.attributesHeader.itemsQuantityIndicator)
    await page.click(selectors.attributesPage.newSectionBtn);

    await test.step('able to cancel rule editing, non applied changes are discarded properly', async() => {
      const orderValueItem = page.locator('.ant-tabs-tab-btn', {hasText: attributeValue})
      await orderValueItem.click()
      await page.click(attributeDetailsSection.editRuleButton)
      await page.click(attributeDetailsSection.ruleDropdown)
      await restrictiveAccessDropdownOption.click()
      await page.click(attributeDetailsSection.cancelEditingButton)
      // reenter editing mode and assert option state is returned to previous one
      await page.click(attributeDetailsSection.editRuleButton)
      await expect(page.locator(attributeDetailsSection.ruleDropdown)).toHaveText('Hierarchical Access')
    })

    await test.step('Update rule and assert saving result', async() => {
      await page.click(attributeDetailsSection.ruleDropdown)
      await restrictiveAccessDropdownOption.click()
      await page.click(attributeDetailsSection.saveChangesButton)
      await expect(ruleUpdatedMsg).toBeVisible()
    })
  });

  test('should edit order value, able to cancel editing', async ({ page, attributeName, attributeValue}) => {
    const orderValueUpdatedMsg = page.locator(selectors.alertMessage, {hasText: `Order value was updated!`})

    await test.step('Create an attribute and assert creation', async() => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await page.click(selectors.attributesPage.attributesHeader.itemsQuantityIndicator)
    await page.click(selectors.attributesPage.newSectionBtn);

    await test.step('Able to cancel editing a value, non-applied changes are discarded properly', async() => {
      const orderValueItem = page.locator('.ant-tabs-tab-btn', {hasText: attributeValue})
      await orderValueItem.click()
      await page.click(attributeDetailsSection.editValueButton)
      await page.fill(attributeDetailsSection.editValueInputField, 'Updated value but not applied')
      await page.click(attributeDetailsSection.cancelEditingButton)
      await page.click(attributeDetailsSection.editValueButton)
      await expect(page.locator(attributeDetailsSection.editValueInputField)).toHaveValue(attributeValue)
    })

    await test.step('Update value and assert result', async() => {
      const updatedOrderValue = 'Updated Value'
      await page.fill(attributeDetailsSection.editValueInputField, updatedOrderValue)
      await page.click(attributeDetailsSection.saveChangesButton)
      await expect(orderValueUpdatedMsg).toBeVisible()
      const updatedOrderValueItem = page.locator('.ant-tabs-tab-btn', {hasText: updatedOrderValue})
      await expect(updatedOrderValueItem).toBeVisible()
    })
  });

  test('should create an attribute with multiple order values, able to edit order of values, able to cancel editing', async ({ page , attributeName, attributeValue}) => {
    const ruleUpdatedMsg = page.locator(selectors.alertMessage, {hasText: `Rule was updated!`})
    const firstOrderItemInEditableList = '.order-list__item >> nth=0'
    const fourthOrderItemInEditableList = '.order-list__item >> nth=3'

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

    await test.step('Should be able to cancel editing of order, non-applied changes are discarded properly', async() => {
      await page.dragAndDrop(fourthOrderItemInEditableList, firstOrderItemInEditableList)
      await expect(page.locator(firstOrderItemInEditableList)).toHaveText(`${attributeValue}4`)
      await page.click(selectors.attributesPage.attributeDetailsSection.cancelEditingButton)
      // reenter editing state and check state
      await page.locator(selectors.attributesPage.attributeDetailsSection.editRuleButton).click()
      await expect(page.locator(firstOrderItemInEditableList)).toHaveText(`${attributeValue}1`)
    })

    await test.step('Edit order of values items using drag-and-drop feature and save changes', async() => {
      await page.dragAndDrop(fourthOrderItemInEditableList, firstOrderItemInEditableList)
      await page.click(selectors.attributesPage.attributeDetailsSection.saveChangesButton)
      await expect(ruleUpdatedMsg).toBeVisible()
    })

    await test.step('Assert proper save of order value change', async() => {
      // filter attributes list to avoid interception
      await page.click(selectors.attributesPage.attributesHeader.filtersToolbarButton)
      await page.fill(selectors.attributesPage.attributesHeader.filterModal.nameInputField, attributeName)
      await page.click(selectors.attributesPage.attributesHeader.filterModal.submitBtn)

      const updatedFirstOrderValue = page.locator('.ant-tabs-tab-btn >> nth=0')
      await expect(updatedFirstOrderValue).toHaveText(`${attributeValue}4`)
    })
  });

  test('Should delete consequent Order field using the Minus icon', async ({ page , attributeName, attributeValue}) => {
    let orderFieldsQuantityAfterAdding: number
    await page.fill(selectors.attributesPage.newSection.attributeNameField, attributeName);
    await page.fill(selectors.attributesPage.newSection.orderField1, attributeValue);

    await test.step('Consequent Order field is properly added', async () => {
      await page.click(selectors.attributesPage.newSection.plusOrderButton)
      const orderFieldsAfterAdding = await page.locator('label[title="Order"]').all()
      orderFieldsQuantityAfterAdding = orderFieldsAfterAdding.length
    })

    await test.step('Order field is properly removed', async () => {
      await page.click(selectors.attributesPage.newSection.minusOrderButton)
      const orderFieldsAfterRemoval = await page.locator('label[title="Order"]').all()
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

  test('should show empty state of the Entitlements table in the Attribute Details section when there are no entitlements', async ({page, attributeName,attributeValue}) => {
    await test.step('Create an attributes', async () => {
      await createAttribute(page, attributeName, [attributeValue])
      await assertAttributeCreatedMsg(page)
    })

    await page.click(selectors.attributesPage.attributesHeader.itemsQuantityIndicator)
    await page.locator(selectors.attributesPage.newSectionBtn).click();

    await test.step('Open Attribute Details section and assert description text', async () => {
      await page.locator('.ant-tabs-tab-btn', {hasText: attributeValue}).click()
      await expect(page.locator('#entitlements-table .ant-empty-description')).toHaveText('No Data')
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
      await page.locator('.ant-tabs-tab-btn', {hasText: attributeValue}).click()
      const tableEntitlements = await page.locator("#entitlements-table .ant-table-tbody").all()
      expect(tableEntitlements.length).toBe(1)
      const tableValue = `${authority}/attr/${attributeName}/value/${attributeValue}`
      await expect(page.locator('.ant-table-cell', {hasText: tableValue})).toBeVisible()
    })
  });

  test('should be able to delete an attribute', async ({ page,attributeName, attributeValue }) => {
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
