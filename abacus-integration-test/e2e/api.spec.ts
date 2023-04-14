import { test } from './helpers/fixtures';
import { APIRequestContext, expect, Page } from "@playwright/test";
import { selectors } from "./helpers/selectors";
import { deleteAttributeViaAPI, deleteAuthorityViaAPI } from "./helpers/operations";

let apiContext: APIRequestContext;
let pageContext;

const getAccessTokenAfterLogin = async (page: Page) => {
    const responsePromise = page.waitForResponse('**/token');

    await page.goto('/');
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

    test('Entitlement Store: Entitle request ', async () => {

        const primaryEntityID = "31c871f2-6d2a-4d27-b727-e619cfaf4e7a";
        const secondaryEntityIDs = "46a871f2-6d2a-4d27-b727-e619cfaf4e7b"

        await test.step('is fulfilled successfully when use valid data', async () => {
            const postEntitleResponse = await apiContext.post('http://localhost:65432/api/entitlement-store/entitle', {
                data: {
                    "primary_entity_id": primaryEntityID,
                    "secondary_entity_ids": [secondaryEntityIDs]
                }
            })
            expect(postEntitleResponse.status()).toBe(200)
            expect(postEntitleResponse.ok()).toBeTruthy()
        })

        await test.step('fails with 422 Unprocessable Entity if use wrong body params', async () => {
            const postEntitleResponse = await apiContext.post('http://localhost:65432/api/entitlement-store/entitle', {
                data: {
                    "invalid_parameter_name": primaryEntityID,
                }
            })
            expect(postEntitleResponse.status()).toBe(422)
        })
    })

    test('KAS App: Healthz request is fulfilled successfully', async () => {
        const kasHealthzResponse = await apiContext.get('http://localhost:65432/api/kas/healthz')
        expect(kasHealthzResponse.status()).toBe(204)
        expect(kasHealthzResponse.ok()).toBeTruthy()
    })

    test('KAS App: Get Version request is fulfilled successful', async () => {
        const kasVersionResponse = await apiContext.get('http://localhost:65432/api/kas')
        expect(kasVersionResponse.status()).toBe(200)
        expect(kasVersionResponse.ok()).toBeTruthy()
    })

    test('KAS App: Get Public Key is accessible and provides certificate key', async () => {
        const getPublicKeyResponse = await apiContext.get('http://localhost:65432/api/kas/kas_public_key');
        expect(getPublicKeyResponse.status()).toBe(200)
        expect(getPublicKeyResponse.ok()).toBeTruthy()
        expect(await getPublicKeyResponse.json()).toContain('BEGIN CERTIFICATE')
    })

    test('Entitlement PDP: Healthz request is fulfilled successfully', async () => {
        const pdpHealthzResponse = await apiContext.get('http://localhost:3355/healthz')
        expect(pdpHealthzResponse.status()).toBe(200)
        expect(pdpHealthzResponse.ok()).toBeTruthy()
    })

    test('Entitlement PDP: Entitlements request ', async () => {

        const primaryEntityID = "508d5145-c16b-4bc7-9b32-a79cbbb17532";
        const secondaryEntityIDs = "46a871f2-6d2a-4d27-b727-e619cfaf4e7b"

        await test.step('is fulfilled successfully when use valid data', async () => {
            const entitlementsResponse = await apiContext.post('http://localhost:3355/entitlements', {
                data: {
                    "primary_entity_id": primaryEntityID,
                    "secondary_entity_ids": [secondaryEntityIDs],
                    "entitlement_context_obj": ""
                }
            })
            expect(entitlementsResponse.status()).toBe(200)
            expect(entitlementsResponse.ok()).toBeTruthy()
        })

        await test.step('fails with 400 Bad Request error if use wrong values for body params', async () => {
            const valueOfWrongFormat = 1
            const badRequestEntitlementsResponse = await apiContext.post('http://localhost:3355/entitlements', {
                data: {
                    "primary_entity_id": valueOfWrongFormat,
                    "secondary_entity_ids": [""],
                    "entitlement_context_obj": ""
                }
            })
            expect(badRequestEntitlementsResponse.status()).toBe(400)
        })

        await test.step('fails with 500 Internal Server Error if use inconsistent body params', async () => {
            const serverErrorEntitlementsResponse = await apiContext.post('http://localhost:3355/entitlements', {
                data: {
                    "primary_entity_id": primaryEntityID,
                    "secondary_entity_ids1": [secondaryEntityIDs],
                    "entitlement_context_obj": ""
                }
            })
            expect(serverErrorEntitlementsResponse.status()).toBe(500)
        })
    })

    test('Entity Resolution: Healthz request is fulfilled successfully', async () => {
        const entityResolutionHealthzResponse = await apiContext.get('http://localhost:7070/healthz')
        expect(entityResolutionHealthzResponse.status()).toBe(200)
        expect(entityResolutionHealthzResponse.ok()).toBeTruthy()
    })

    test('Entity Resolution: Resolve request ', async () => {
        await test.step('is fulfilled successfully when use valid data', async () => {
            const resolveResponse = await apiContext.post('http://localhost:7070/resolve', {
                data: {
                    "entity_identifiers": [
                        {"identifier": "bob@sample.org", "type": "username"},
                        {"identifier": "alice@sample.org", "type": "email"}
                    ]
                }
            })
            expect(resolveResponse.status()).toBe(200)
            expect(resolveResponse.ok()).toBeTruthy()
        })

        await test.step('fails with 400 Bad Request error if use wrong Type value', async () => {
            const badRequestResolveResponse = await apiContext.post('http://localhost:7070/resolve', {
                data: {
                    "entity_identifiers": [
                        {"identifier": "bob@sample.org", "type": "somewrongtype"}
                    ]
                }
            })
            expect(badRequestResolveResponse.status()).toBe(400)
        })
    })
})
