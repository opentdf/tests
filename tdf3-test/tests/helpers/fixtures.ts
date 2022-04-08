import { test as baseTest } from "@playwright/test";

export const generateRandomDigit = (max = 10, min = 0) =>
  Math.floor(Math.random() * max + min);

export const test = baseTest.extend<{ attributeName: string; authority: string; attributeValue: string; }>({
  authority: async ({ page }, use) => {
    const authority = `https://opentdf${generateRandomDigit(100, 1)}.ua`;

    await use(authority);
  }
});
