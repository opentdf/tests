import { test } from './helpers/fixtures';
import { APIRequestContext, chromium, expect, Page } from "@playwright/test";
import { selectors } from "./helpers/selectors";
import {deleteAttributeViaAPI, deleteAuthorityViaAPI, getAccessToken} from "./helpers/operations";

let apiContext: APIRequestContext;
let pageContext;

const getAccessTokenAfterLogin = async (page: Page) => {
    const responsePromise = page.waitForResponse('**/token');

    await page.goto('http://localhost:65432/');
    await page.locator(selectors.loginButton).click()
    await page.fill(selectors.loginScreen.usernameField, "user1");
    await page.fill(selectors.loginScreen.passwordField, "testuser123");
    await page.click(selectors.loginScreen.submitButton);

    const response = await responsePromise;
    const jsonResponse = await response.json();

    return jsonResponse.access_token;
};

test.describe('API:', () => {
    test.beforeEach(async ({ playwright, authority, browser }) => {
        pageContext = await browser.newContext();
        const page = await pageContext.newPage();
        const authToken = await getAccessTokenAfterLogin(page)

        apiContext = await playwright.request.newContext({
            // baseURL: 'http://localhost:65432/api',
            extraHTTPHeaders: {
                'Authorization': `Bearer ${authToken}`,
            },
        });

        await test.step('Create mandatory authority', async () => {
            const createAuthorityResponse = await apiContext.post('http://localhost:65432/api/attributes/authorities', {
                data: {
                    "authority": authority
                },
            })
            expect(createAuthorityResponse.status()).toBe(200)
            expect(createAuthorityResponse.ok()).toBeTruthy()
        })
    })

    test.afterEach(async ({ authority}) => {
        await deleteAuthorityViaAPI(apiContext, authority)
    })

    test.afterAll(async ({ }) => {
        await apiContext.dispose();
    });

    test('Attributes: create, read, update, delete', async ({authority, attributeName}) => {

        const originalAttributeData = {
            "authority": authority,
            "name": attributeName,
            "rule": "hierarchy",
            "state": "published",
            "order": [
                "TradeSecret"
            ]
        }

        const updatedAttributeData = {
            "authority": authority,
            "name": attributeName,
            "rule": "anyOf",
            "state": "published",
            "order": [
                "Proprietary",
                "BusinessSensitive"
            ]
        }

        await test.step('CREATE attribute and assert result', async () => {
            const createAttributeResponse = await apiContext.post('http://localhost:65432/api/attributes/definitions/attributes', {
                data: originalAttributeData
            })
            expect(createAttributeResponse.status()).toBe(200)
            expect(createAttributeResponse.ok()).toBeTruthy()
        })

        await test.step('GET all attributes and assert result', async () => {
            const getAttributesResponse = await apiContext.get(`http://localhost:65432/api/attributes/definitions/attributes?authority=${authority}`, {
                params: {
                    name: attributeName
                }
            })
            expect(getAttributesResponse.status()).toBe(200)
            expect(getAttributesResponse.ok()).toBeTruthy()
            const getAttributesResponseBody = await getAttributesResponse.json();
            await expect(getAttributesResponseBody).toMatchObject([originalAttributeData])
        })

        await test.step('UPDATE attribute and assert result', async () => {
            const updateAttributeResponse = await apiContext.put('http://localhost:65432/api/attributes/definitions/attributes', {
                data: updatedAttributeData
            })
            expect(updateAttributeResponse.status()).toBe(200)
            expect(updateAttributeResponse.ok()).toBeTruthy()
            const updateAttributesResponseBody = await updateAttributeResponse.json();
            expect(updateAttributesResponseBody).toMatchObject(updatedAttributeData)
        })

        await test.step('DELETE attribute and assert result', async () => {
            await deleteAttributeViaAPI(apiContext, authority, attributeName, ["Proprietary", "BusinessSensitive"], "anyOf")
        })
    })

    test('Entitlements: create, read, delete', async ({ authority, attributeName, attributeValue}) => {

        let existedEntityId: string;
        const entitlementPayload = `${authority}/attr/${attributeName}/value/${attributeValue}`;

        await test.step('GET Entitlements to parse existed entityID', async () => {
            const getEntitlementsResponse = await apiContext.get(`http://localhost:65432/api/entitlements/entitlements`)
            expect(getEntitlementsResponse.status()).toBe(200)
            expect(getEntitlementsResponse.ok()).toBeTruthy()

            // Get ID of existed entity to work with (response returns list of ordered maps)
            const getEntitlementsResponseBody = await getEntitlementsResponse.json()
            const firstEntity = getEntitlementsResponseBody[0]
            existedEntityId = Object.keys(firstEntity)[0]
        })

        await test.step('CREATE Entitlement and assert result', async () => {
            const createAttributeResponse = await apiContext.post(`http://localhost:65432/api/entitlements/entitlements/${existedEntityId}`, {
                data: [entitlementPayload]
            })
            expect(createAttributeResponse.status()).toBe(200)
            expect(createAttributeResponse.ok()).toBeTruthy()
        })

        await test.step('GET and check created entitlement', async () => {
            const checkCreatedEntitlementResponse = await apiContext.get(`http://localhost:65432/api/entitlements/entitlements?entityId=${existedEntityId}`)
            expect(checkCreatedEntitlementResponse.status()).toBe(200)
            expect(checkCreatedEntitlementResponse.ok()).toBeTruthy()

            const checkCreatedEntitlementResponseBody = await checkCreatedEntitlementResponse.text()
            expect(checkCreatedEntitlementResponseBody).toContain(existedEntityId)
            expect(checkCreatedEntitlementResponseBody).toContain(entitlementPayload)
        })

        await test.step('DELETE entitlement and assert result', async () => {
            const deleteEntitlementResponse = await apiContext.delete(`http://localhost:65432/api/entitlements/entitlements/${existedEntityId}`, {
                data: [entitlementPayload]
            })
            expect(deleteEntitlementResponse.status()).toBe(202)
            expect(deleteEntitlementResponse.ok()).toBeTruthy()
        })
    })
})
