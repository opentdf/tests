import { test } from './helpers/fixtures';
import { APIRequestContext, expect } from "@playwright/test";
import {deleteAttributeViaAPI, deleteAuthorityViaAPI, removeAllAttributesOfAuthority} from "./helpers/operations";

let apiContext: APIRequestContext;
let existedEntityId = "31c871f2-6d2a-4d27-b727-e619cfaf4e7a";

const createAuthority = async (authorityName) => {
    const createAuthorityResponse = await apiContext.post('http://localhost:65432/api/attributes/authorities', {
        data: {
            "authority": authorityName
        },
    })
    return createAuthorityResponse
}

const getAccessTokenViaAPI = async (playwright, client_id, client_secret) => {
    const apiContextForGetTokenCall = await playwright.request.newContext();
    const urlencodedFormData = new URLSearchParams();
    urlencodedFormData.append('grant_type', 'client_credentials');
    urlencodedFormData.append('client_id', client_id);
    urlencodedFormData.append('client_secret', client_secret);

    const getAccessTokenResponse = await apiContextForGetTokenCall.post('http://localhost:65432/auth/realms/tdf/protocol/openid-connect/token', {
        headers:{
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        data: urlencodedFormData.toString()
    })

    const responseBody = await getAccessTokenResponse.json()
    return responseBody.access_token;
};

test.describe('API:', () => {
    test.beforeEach(async ({ playwright, authority }) => {
        const authToken = await getAccessTokenViaAPI(playwright, 'tdf-client', '123-456')

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
        await removeAllAttributesOfAuthority(apiContext, authority);
        const deleteAuthorityResponse = await deleteAuthorityViaAPI(apiContext, authority)
        await expect(deleteAuthorityResponse.status()).toBe(202)
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

    test('Attribute with already existed name cannot be created for the same authority', async ({authority, attributeName}) => {
        const attributeData = {
            "authority": authority,
            "name": attributeName,
            "rule": "hierarchy",
            "state": "published",
            "order": [
                "TradeSecret"
            ]
        }
        const createAttributeResponse = await apiContext.post('http://localhost:65432/api/attributes/definitions/attributes', {
            data: attributeData
        })
        expect(createAttributeResponse.ok()).toBeTruthy()

        const createDuplicatedAttributeResponse = await apiContext.post('http://localhost:65432/api/attributes/definitions/attributes', {
            data: attributeData
        })
        expect(createDuplicatedAttributeResponse.status()).toBe(400)
    })

    test('Attribute creation is failed when do not fill required authority parameter', async ({authority, attributeName}) => {
        const attributeDataWithMissingAuthority = {
            "authority": "",
            "name": attributeName,
            "rule": "hierarchy",
            "state": "published",
            "order": [
                "TradeSecret"
            ]
        }
        const createAttributeResponse = await apiContext.post('http://localhost:65432/api/attributes/definitions/attributes', {
            data: attributeDataWithMissingAuthority
        })
        expect(createAttributeResponse.status()).toBe(422)
    })

    // TODO: backend validation of required parameters is absent, server returns 200 when request should fail
    test.skip('Attribute creation is failed when do not fill required Name, Order, Rule fields', async ({authority}) => {
        const attributeDataWithMissingName = {
            "authority": authority,
            "name": "",
            "rule": "",
            "state": "published",
            "order": [
                ""
            ]
        }
        const createAttributeResponse = await apiContext.post('http://localhost:65432/api/attributes/definitions/attributes', {
            data: attributeDataWithMissingName
        })
        expect(createAttributeResponse.status()).toBe(422)
    })

    test('Attribute creation is failed when use wrong body data type', async ({authority, attributeName}) => {
        const attributeData = {
            "authority": authority,
            "name": attributeName,
            "rule": "hierarchy",
            "state": "published",
            "order": [
                "TradeSecret"
            ]
        }
        const createAttributeResponse = await apiContext.post('http://localhost:65432/api/attributes/definitions/attributes', {
            headers: {
                'Content-Type': 'application/html'
            },
            data: attributeData
        })
        expect(createAttributeResponse.status()).toBe(422)
    })

    test('Attribute creation is failed when attribute data is empty', async () => {
        const createAttributeResponse = await apiContext.post('http://localhost:65432/api/attributes/definitions/attributes', {
            data: {}
        })
        expect(createAttributeResponse.status()).toBe(422)
    })

    test('Get Attribute Authorities is fulfilled successfully', async ({authority}) => {
        const getAuthoritiesResponse = await apiContext.get('http://localhost:65432/api/attributes/authorities')
        expect(getAuthoritiesResponse.status()).toBe(200)
        expect(getAuthoritiesResponse.ok()).toBeTruthy()
        expect(await getAuthoritiesResponse.json()).toContain(authority)
    })

    test('Attributes-related request is failed when client does not have necessary audience access', async ({playwright, request}) => {
        const authTokenWithEntitlementsOnlyAudience = await getAccessTokenViaAPI(playwright, 'tdf-test-entitlements', '123-456')
        const getEntitlementsResponse = await request.get('http://localhost:65432/api/entitlements/entitlements', {
            headers: {
                'Authorization': `Bearer ${authTokenWithEntitlementsOnlyAudience}`
            }
        })
        expect(getEntitlementsResponse.status()).toBe(200)

        const getAuthoritiesResponse = await request.get('http://localhost:65432/api/attributes/definitions/attributes', {
            headers: {
                'Authorization': `Bearer ${authTokenWithEntitlementsOnlyAudience}`
            }
        })
        expect(getAuthoritiesResponse.status()).toBe(401)
    })

    test('Create Attribute Authority is failed when use empty name, name of non-url or inconsistent format', async () => {
        await test.step('Create Authority is failed when use blank name', async () => {
            const blankAuthorityName = ""
            const createAuthorityResponse = await createAuthority(blankAuthorityName)
            expect(createAuthorityResponse.status()).toBe(422)

            const createAuthorityResponse2 = await createAuthority(null)
            expect(createAuthorityResponse2.status()).toBe(422)
        })

        await test.step('Create Attribute Authority is failed when use name of non-url format', async () => {
            const authorityNameOfNonUrlFormat = "authorityName"
            const createAuthorityResponse = await createAuthority(authorityNameOfNonUrlFormat)
            expect(createAuthorityResponse.status()).toBe(422)
        })

        await test.step('Create Attribute Authority is failed when use name of inconsistent format', async () => {
            const authorityNameOfWrongType = 0
            const createAuthorityResponse = await createAuthority(authorityNameOfWrongType)
            expect(createAuthorityResponse.status()).toBe(422)
        })
    })

    test('Create Attribute Authority is failed when try to use name of already existed authority', async ({authority}) => {
        const recreateAuthorityResponse = await createAuthority(authority)
        expect(recreateAuthorityResponse.status()).toBe(400)
    })

    test('Delete Attribute Authority is failed when use non-existed authority name', async () => {
        const nonExistedAuthority = "https://nonexisted.com"
        const deleteAuthorityResponse = await deleteAuthorityViaAPI(apiContext, nonExistedAuthority)
        expect(deleteAuthorityResponse.status()).toBe(404)
    })

    test('Delete Attribute request is failed when invalid auth token is used', async ({request}) => {
        const validAuthorityName = "https://valid.com"
        const invalidToken = "bnh5yzdirjinqaorq0ox1tf383nb3xr"
        const deleteAuthorityResponse = await request.delete('http://localhost:65432/api/attributes/authorities',{
            headers: {
                'Authorization': `Bearer ${invalidToken}`
            },
            data: {
                "authority": validAuthorityName
            },
        });

        expect(deleteAuthorityResponse.status()).toBe(401)
    })

    test('Entitlements: create, read, delete', async ({ authority, attributeName, attributeValue}) => {
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

    test('Entitlements request fails with Not Allowed error when using wrong HTTP method', async () => {
        const entitlementsResponseWithWrongMethodUsed = await apiContext.post(`http://localhost:65432/api/entitlements/entitlements`)
        expect(entitlementsResponseWithWrongMethodUsed.status()).toBe(405)
    })

    test('Create Entitlements request fails when using payload of inconsistent format', async ({ authority, attributeName, attributeValue}) => {
        await test.step('Fails with 400 error when using wrong entitlement format', async () => {
            const wrongFormatOfEntitlementValue = `${authority}/a/${attributeName}/v/${attributeValue}`;
            const createAttributeResponse = await apiContext.post(`http://localhost:65432/api/entitlements/entitlements/${existedEntityId}`, {
                data: [wrongFormatOfEntitlementValue]
            })
            expect(createAttributeResponse.status()).toBe(400)
        })

        await test.step('Fails with Unprocessable Entity error when using wrong payload format', async () => {
            const singleEntitlement = `${authority}/attr/${attributeName}/value/${attributeValue}`;
            const createAttributeResponse = await apiContext.post(`http://localhost:65432/api/entitlements/entitlements/${existedEntityId}`, {
                data: `${singleEntitlement}`
            })
            expect(createAttributeResponse.status()).toBe(422)
        })
    })

    test('Entitlements request fails when use non-existed EntityID', async ({authority, attributeName,attributeValue}) => {
        const entitlementPayload = `${authority}/attr/${attributeName}/value/${attributeValue}`;
        const nonExistedEntityId = "x-x-x-x"
        const createAttributeResponse = await apiContext.post(`http://localhost:65432/api/entitlements/entitlements/${nonExistedEntityId}`, {
            data: `${entitlementPayload}`
        })
        expect(createAttributeResponse.status()).toBe(422)
    })

    test('Delete Entitlements request fails when using wrong payload media type', async ({ authority, attributeName, attributeValue}) => {
        const entitlementValue = `${authority}/attr/${attributeName}/value/${attributeValue}`;
        const deleteAttributeResponse = await apiContext.delete(`http://localhost:65432/api/entitlements/entitlements/${existedEntityId}`, {
            headers: {
                'Content-Type': 'application/xml'
            },
            data: [entitlementValue]
        })
        expect(deleteAttributeResponse.status()).toBe(422)
    })

    test('Entitlement Store: Entitle request ', async () => {
        const primaryEntityID = "31c871f2-6d2a-4d27-b727-e619cfaf4e7a";
        const secondaryEntityIDs = "46a871f2-6d2a-4d27-b727-e619cfaf4e7b"

        await test.step('is fulfilled successfully when use valid data', async () => {
            const postEntitleResponse = await apiContext.post('http://localhost:65432/api/entitlement-store/entitle', {
                data: {
                    "primary_entity_id": existedEntityId,
                    "secondary_entity_ids": [secondaryEntityIDs]
                }
            })
            expect(postEntitleResponse.status()).toBe(200)
            expect(postEntitleResponse.ok()).toBeTruthy()
            if (existedEntityId !== primaryEntityID) {
                const postEntitleResponseBody = await postEntitleResponse.json()
                expect(postEntitleResponseBody[0].entity_attributes[0].attribute).not.toBe(null)
            }
        })

        await test.step('fails with 422 Unprocessable Entity if use wrong body params', async () => {
            const postEntitleResponse = await apiContext.post('http://localhost:65432/api/entitlement-store/entitle', {
                data: {
                    "invalid_parameter_name": existedEntityId,
                }
            })
            expect(postEntitleResponse.status()).toBe(422)
        })
    })

    const KAS_VERSION = process.env.KAS_VERSION || "python-kas"
    // endpoint is available only for python KAS
    if (KAS_VERSION == "python-kas") {
        test('KAS App: Healthz request is fulfilled successfully', async () => {
            const kasHealthzResponse = await apiContext.get('http://localhost:65432/api/kas/healthz')
            expect(kasHealthzResponse.status()).toBe(204)
            expect(kasHealthzResponse.ok()).toBeTruthy()
        })
    }

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
        await test.step('is fulfilled successfully when use valid data, matching entity is returned with ID', async () => {
            const resolveResponse = await apiContext.post('http://localhost:7070/resolve', {
                data: {
                    "entity_identifiers": [
                        {"identifier": "alice_1234", "type": "username"}
                    ]
                }
            })
            expect(resolveResponse.status()).toBe(200)
            expect(resolveResponse.ok()).toBeTruthy()
            const resolveResponseBody = await resolveResponse.json()
            expect(resolveResponseBody[0].EntityRepresentations[0].id).toBeTruthy()
        })

        // cover PLAT-2439 case
        await test.step('returns no entity when use partially matching non-existent identifier', async () => {
            const nonExistentButPartiallyMatchingIdentifier = "alice_12@test.test"
            const resolveResponseNoMatchCase = await apiContext.post('http://localhost:7070/resolve', {
                data: {
                    "entity_identifiers": [
                        {"identifier": nonExistentButPartiallyMatchingIdentifier, "type": "email"}
                    ]
                }
            })
            expect(resolveResponseNoMatchCase.status()).toBe(200)
            expect(resolveResponseNoMatchCase.ok()).toBeTruthy()
            const resolveResponseBody = await resolveResponseNoMatchCase.json()
            expect(resolveResponseBody[0].EntityRepresentations).toBe(null)
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
