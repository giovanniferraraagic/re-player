import { test, expect } from '@playwright/test';

/**
 * Placeholder test committed so the Playwright project is verifiably green
 * before the harness generates anything. It is not generated output.
 */
test('target application is reachable', async ({ page }) => {
  // Relative './' keeps the baseURL path; a leading '/' would resolve to the domain root.
  await page.goto('./');
  await expect(page.getByRole('heading', { name: 'todos' })).toBeVisible();
});
