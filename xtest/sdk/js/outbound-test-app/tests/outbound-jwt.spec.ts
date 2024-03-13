import { test, expect } from '@playwright/test';
import * as jwt from 'jsonwebtoken';
import { readFileSync } from 'node:fs';

const privateKey = readFileSync('private.pem');
const header = {
  "alg": "RS256",
  "typ": "JWT",
  "kid": "hYA0Dmc5HaXhCgNGMa-uG3UHUnLaTgrVgO1W2e7BeYM"
};

const payload = {
  "exp": 1710250757,
  "iat": 1710250457,
  "auth_time": 1710250453,
  "jti": "164618ab-e3ce-40d8-9ab6-d23245398397",
  "iss": "http://localhost:65432/auth/realms/tdf",
  "aud": [
    "tdf-entitlement",
    "tdf-attributes",
    "realm-management",
    "account"
  ],
  "sub": "32b8643b-e9ed-445d-93a4-878be10b4300",
  "typ": "Bearer",
  "azp": "dcr-test",
  "nonce": "327fda7a-a940-4f0d-96f8-225fe451a39c",
  "session_state": "1203b7c5-947d-4c8a-9190-b8a9ab793bba",
  "acr": "1",
  "allowed-origins": [
    "https://local.virtru.com",
    "http://localhost:65432"
  ],
  "realm_access": {
    "roles": [
      "default-roles-tdf",
      "offline_access",
      "uma_authorization"
    ]
  },
  "resource_access": {
    "realm-management": {
      "roles": [
        "view-users",
        "view-clients",
        "query-clients",
        "query-groups",
        "query-users"
      ]
    },
    "account": {
      "roles": [
        "manage-account",
        "manage-account-links",
        "view-profile"
      ]
    }
  },
  "scope": "openid profile email",
  "sid": "1203b7c5-947d-4c8a-9190-b8a9ab793bba",
  "email_verified": false,
  "tdf_claims": {
    "entitlements": [
      {
        "entity_identifier": "32b8643b-e9ed-445d-93a4-878be10b4300",
        "entity_attributes": [
          {
            "attribute": "https://example.org/attr/OPA/value/AddedByOPA",
            "displayName": "Added By OPA"
          }
        ]
      },
      {
        "entity_identifier": "d6107f89-c484-45e6-ba1f-2c500404b75f",
        "entity_attributes": [
          {
            "attribute": "https://example.org/attr/OPA/value/AddedByOPA",
            "displayName": "Added By OPA"
          }
        ]
      }
    ],
    "client_public_signing_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAw6pUHCSNEHa8P9KavSxJ\ndFJs/v865kWiggypLNZx2T7VjT5RFhHde30oFaLBxE+PEMbGc078sVe08VV/eUuz\nNlfVJJzz02mEzvNJAZrd7enhjQB4E27CsF08hAxC17MjdlCaQ+wmFs//8Ds4JDM7\norteP2yyZS3NgNl9CBfM4AP/ASzNWpfVkMNRM2PPrb09XBiEMMWgwOHa63EJwFfX\nSRcAK+2JVOVPRdtP78QtrFHxVzyT+O1+QXRcD8uGpYAROZWEGnmhRbkByAGTn2D5\nTozgO1xzrUzcIonXt0KP1MuKayROE1VWtfASms4pXbbFYmj8MNKhE8jLidZyefnj\nTwIDAQAB\n-----END PUBLIC KEY-----\n"
  },
  "preferred_username": "user1"
};
const token = jwt.sign(payload, privateKey, { algorithm: 'RS256', header });

test.describe.configure({ mode: 'serial' });

test('Check invalidToken JWT', async ({ page }) => {
  await page.goto('https://local.virtru.com/');
  await page.waitForURL('/');
  await page.getByRole('button', { name: 'Login' }).click();
  await page.getByLabel('Username or email').fill('user1');
  await page.getByLabel('Password').fill('testuser123');
  await page.getByRole('button', { name: 'Sign In' }).click();

  const responsePromise = page.waitForResponse('**/api/kas/v2/rewrap');

  await page.route('**/api/kas/v2/rewrap', async route => {
    const headers = route.request().headers();
    headers['Authorization'] = "Bearer invalidToken";
    await route.continue({ headers });
  });

  await page.getByRole('button', { name: 'Test' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(401)
});

let user1HeaderAuth;

test('Check valid JWT signed by unknown key', async ({ page }) => {
  await page.goto('https://local.virtru.com/');
  await page.waitForURL('/');
  await page.getByRole('button', { name: 'Login' }).click();
  await page.getByLabel('Username or email').fill('user1');
  await page.getByLabel('Password').fill('testuser123');
  await page.getByRole('button', { name: 'Sign In' }).click();

  const responsePromise = page.waitForResponse('**/api/kas/v2/rewrap');

  await page.route('**/api/kas/v2/rewrap', async route => {
    const headers = route.request().headers();
    user1HeaderAuth = headers.authorization;
    headers['authorization'] = `Bearer ${token}`;
    await route.continue({ headers });
  });

  await page.getByRole('button', { name: 'Test' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(401)
});

test('Check valid and properly signed JWT and copied from previous session', async ({ page }) => {
  await page.goto('https://local.virtru.com/');
  await page.waitForURL('/');
  await page.getByRole('button', { name: 'Login' }).click();
  await page.getByLabel('Username or email').fill('user2');
  await page.getByLabel('Password').fill('testuser123');
  await page.getByRole('button', { name: 'Sign In' }).click();

  const responsePromise = page.waitForResponse('**/api/kas/v2/rewrap');

  await page.route('**/api/kas/v2/rewrap', async route => {
    const headers = route.request().headers();
    headers['authorization'] = user1HeaderAuth;
    await route.continue({ headers });
  });

  await page.getByRole('button', { name: 'Test' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(401)
});