/**
 * An unreachable app is INFRASTRUCTURE, not a test result.
 *
 * Same rule the API layer follows (tests/api/conftest.py): if the server isn't
 * serving, abort once with a clear message rather than letting every UI test
 * fail at `page.goto` and read like a pile of application bugs.
 */
const BASE_URL = process.env.MUNICIPAL_AI_BASE_URL || 'http://localhost:8000';

export default async function globalSetup() {
  let res: Response;
  try {
    res = await fetch(BASE_URL + '/', {
      signal: AbortSignal.timeout(15_000),
    });
  } catch (err) {
    throw new Error(
      `INFRASTRUCTURE: no server at ${BASE_URL} (${(err as Error).message}). ` +
        'Start the app before running the UI layer — this is not a test failure.'
    );
  }
  if (res.status >= 500) {
    throw new Error(
      `INFRASTRUCTURE: ${BASE_URL}/ returned ${res.status}. ` +
        'The app is up but erroring at the root — fix that before reading this layer.'
    );
  }
}
