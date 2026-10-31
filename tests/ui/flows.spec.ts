/**
 * UI flows for municipal_ai.
 *
 * Every selector and route below was read off the rendered DOM of the running
 * app, not guessed from the app's shape. The previous version of this file
 * navigated to /complaints/new (404 — the route is /complaint/) and drove the
 * complaint form with getByLabel(), which cannot work: the form is a 4-step
 * wizard whose visible inputs are unlabelled and whose POST values live in
 * mirrored hidden inputs.
 *
 * Quotas that shape this file (per IP, per hour):
 *   /api/chat/ + /api/chat/stream/   120      complaint POST   3
 * Anything that spends the complaint quota is opt-in via RUN_WRITE_TESTS=1, so
 * a loop can run this suite repeatedly without exhausting it.
 */
import { test, expect, Page } from '@playwright/test';

const WRITE_TESTS = process.env.RUN_WRITE_TESTS === '1';

/* ─────────────────────── Homepage AI bar ─────────────────────── */

test.describe('Homepage AI bar', () => {
  test('answers a municipal question with a real answer', async ({ page }) => {
    await page.goto('/');

    await page.locator('#heroQuery').fill('How do I file a complaint about a broken road?');
    await page.locator('#heroAskBtn').click();

    const answer = page.locator('#aiResponseText');
    await expect(answer).toBeVisible({ timeout: 60_000 });
    // The spinner hides only once the first token lands.
    await expect(page.locator('#aiLoading')).toBeHidden({ timeout: 60_000 });

    const text = ((await answer.textContent()) || '').trim();
    expect(text, 'AI bar rendered an empty answer').not.toBe('');
    expect(
      text,
      `AI bar showed its error fallback instead of an answer: ${text}`
    ).not.toMatch(/could not process your request/i);
    // Fallback guard: the keyword-matcher path produces stub-length replies.
    expect(
      text.split(/\s+/).length,
      `Answer was only ${text.split(/\s+/).length} words — suspect the keyword fallback: ${text.slice(0, 120)}`
    ).toBeGreaterThan(15);
  });

  test('shows an error message, not a blank panel, when the API fails', async ({ page }) => {
    // askAI() tries /api/chat/stream/ first and falls back to /api/chat/.
    // Both have to fail for the user-visible error path to be exercised.
    await page.route('**/api/chat/stream/', (route) => route.fulfill({ status: 500, body: '{}' }));
    await page.route('**/api/chat/', (route) => route.fulfill({ status: 500, body: '{}' }));

    await page.goto('/');
    await page.locator('#heroQuery').fill('test');
    await page.locator('#heroAskBtn').press('Enter');

    await expect(page.locator('#aiResponseText')).toHaveText(
      /could not process your request/i,
      { timeout: 30_000 }
    );
    // The button must return to its resting state or the widget is stuck.
    await expect(page.locator('#heroAskBtn')).toBeEnabled({ timeout: 30_000 });
  });

  test('an empty question does not open the response panel', async ({ page }) => {
    await page.goto('/');
    await page.locator('#heroAskBtn').click();
    await expect(page.locator('#aiResponseContainer')).toBeHidden();
  });
});

/* ─────────────────── Complaint wizard (/complaint/) ─────────────────── */

/** Drive the wizard from step 1 to the review step. */
async function fillWizard(page: Page, title: string, description: string) {
  await page.locator('.rp-cat-card[data-val="ROAD"]').click();
  await page.locator('#btn-next-1').click();
  await expect(page.locator('#step-2')).toHaveClass(/active/);

  await page.locator('#in-title').fill(title);
  await page.locator('#in-desc').fill(description);
  await page.locator('#btn-next-2').click();
  await expect(page.locator('#step-3')).toHaveClass(/active/);

  await page.locator('#in-location').fill('Durbar Square');
  await page.locator('#in-ward').selectOption('5');
  await page.locator('#in-name').fill('QA Bot');
  await page.locator('#in-email').fill('qa@example.com');
  await page.locator('#btn-next-3').click();
  await expect(page.locator('#step-4')).toHaveClass(/active/);
}

test.describe('Complaint wizard', () => {
  test('blocks step 1 until a category is chosen', async ({ page }) => {
    await page.goto('/complaint/');
    await page.locator('#btn-next-1').click();

    await expect(page.locator('#cat-err-msg')).toBeVisible();
    await expect(
      page.locator('#step-1'),
      'wizard advanced past step 1 with no category selected'
    ).toHaveClass(/active/);
  });

  test('blocks step 2 until the title and description are long enough', async ({ page }) => {
    await page.goto('/complaint/');
    await page.locator('.rp-cat-card[data-val="ROAD"]').click();
    await page.locator('#btn-next-1').click();
    await expect(page.locator('#step-2')).toHaveClass(/active/);

    // Title needs >= 5 chars, description >= 20.
    await page.locator('#in-title').fill('road');
    await page.locator('#in-desc').fill('too short');
    await page.locator('#btn-next-2').click();

    await expect(
      page.locator('#step-2'),
      'wizard advanced past step 2 with an under-length title and description'
    ).toHaveClass(/active/);
    await expect(page.locator('#err-title')).toBeVisible();
  });

  test('reaches the review step and shows what will be submitted', async ({ page }) => {
    await page.goto('/complaint/');
    await fillWizard(
      page,
      'Pothole on Durbar Square approach road',
      'A large pothole has opened on the approach road and is a hazard to pedestrians.'
    );

    // The review step must echo the real values, not placeholders.
    await expect(page.locator('#rv-title')).toHaveText(/Pothole on Durbar Square/);
    await expect(page.locator('#btn-submit')).toBeVisible();
  });

  test('submits and issues a BK- tracking ID', async ({ page }) => {
    test.skip(
      !WRITE_TESTS,
      'write test: set RUN_WRITE_TESTS=1 (complaint POST is capped at 3/hour per IP)'
    );

    await page.goto('/complaint/');
    await fillWizard(
      page,
      'QA UI test — please ignore',
      'Automated UI test submission from tests/ui/flows.spec.ts. Safe to close.'
    );
    // This POST is genuinely slow: submit_complaint() sends the confirmation
    // email synchronously, then calls categorize_complaint_async.delay(), which
    // blocks on broker retries whenever Celery is down (normal on a dev box).
    // Measured past the 15s default, so the click gets its own budget.
    await page.locator('#btn-submit').click({ timeout: 60_000 });

    const body = page.locator('body');
    await expect(body).toContainText(/BK-[A-Z0-9]+|too many submissions/i, { timeout: 60_000 });

    if (/too many submissions/i.test((await body.textContent()) || '')) {
      test.skip(true, 'complaint submission: hourly quota of 3/IP already spent, not a defect');
    }
    await expect(page.locator('#rp-id-text')).toHaveText(/BK-[A-Z0-9]+/);
  });
});

/* ──────────────────── Business directory ──────────────────── */

test.describe('Business directory', () => {
  test('lists businesses', async ({ page }) => {
    await page.goto('/businesses/');
    // Non-empty guard: an empty grid is a data outage, not a pass. The Sep 15
    // database loss looked exactly like this.
    await expect(page.locator('.biz-card').first()).toBeVisible();
  });

  test('search returns a working page, not an error or a blank grid', async ({ page }) => {
    await page.goto('/businesses/');
    await page.locator('input[name="q"][placeholder*="business" i]').fill('a');
    await page.keyboard.press('Enter');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('body')).not.toContainText(/server error|traceback/i);
    // The search form must survive its own round-trip.
    await expect(page.locator('input[name="q"][placeholder*="business" i]')).toHaveValue('a');
  });
});
