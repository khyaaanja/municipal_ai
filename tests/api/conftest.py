"""
Shared fixtures for the API smoke layer.

Two rules this layer is built around, learned the hard way:

1. An unreachable server is INFRASTRUCTURE, not a test result. If the app isn't
   up we abort the whole session with one clear message instead of emitting a
   dozen confusing connection errors that read like application bugs.
2. A test that can pass while the feature is missing is worse than no test.
   Nothing here asserts `status != 500` or hides an assertion behind
   `if status == 200`. Where a real quota (not a defect) blocks us, we SKIP
   with a stated reason so it shows up as a skip, never as a pass.
"""
import os

import pytest
import requests

DEFAULT_BASE_URL = "http://localhost:8000"

# Endpoints with per-IP hourly quotas. This suite is designed to run in a loop
# (run_test_loop.sh), so anything that burns quota is opt-in or skips honestly.
#   /api/chat/      120/hr      /api/scan/  30/hr
#   /complaint/ POST  3/hr      /api/voice/ 60/hr
RATE_LIMITED_NOTE = "endpoint returned 429 (per-IP hourly quota), not a defect"


def pytest_configure(config):
    config.addinivalue_line("markers", "write: mutates state or burns a tight quota; opt in with RUN_WRITE_TESTS=1")
    config.addinivalue_line("markers", "quota: consumes a per-IP hourly quota")
    config.addinivalue_line("markers", "hardening: production-only expectations; opt in with EXPECT_PROD_HARDENING=1")


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("MUNICIPAL_AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture(scope="session", autouse=True)
def _server_reachable(base_url):
    """Abort the run (not fail every test) when the app isn't serving."""
    try:
        r = requests.get(base_url + "/", timeout=10)
    except requests.RequestException as exc:
        pytest.exit(
            f"INFRASTRUCTURE: no server at {base_url} ({exc.__class__.__name__}). "
            "Start the app before running the API layer — this is not a test failure.",
            returncode=3,
        )
    if r.status_code >= 500:
        pytest.exit(
            f"INFRASTRUCTURE: {base_url}/ returned {r.status_code}. "
            "The app is up but erroring at the root — fix that before reading this layer.",
            returncode=3,
        )


class Client:
    """requests.Session with Django CSRF handling wired in.

    The app protects its JSON endpoints with CsrfViewMiddleware, which is
    correct for a same-origin browser widget. So the tests acquire a token the
    way a browser does rather than asking the app to drop the protection.
    """

    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        # /chat/ is decorated @ensure_csrf_cookie, so this seeds the cookie.
        self.session.get(base_url + "/chat/", timeout=20)

    @property
    def csrf_token(self):
        return self.session.cookies.get("csrftoken")

    def get(self, path, **kw):
        kw.setdefault("timeout", 30)
        return self.session.get(self.base_url + path, **kw)

    def post_json(self, path, payload, csrf=True, **kw):
        kw.setdefault("timeout", 90)
        headers = dict(kw.pop("headers", {}))
        if csrf:
            headers["X-CSRFToken"] = self.csrf_token or ""
            headers["Referer"] = self.base_url
        return self.session.post(self.base_url + path, json=payload, headers=headers, **kw)

    def post_form(self, path, data, csrf=True, **kw):
        kw.setdefault("timeout", 60)
        payload = dict(data)
        headers = dict(kw.pop("headers", {}))
        if csrf:
            payload["csrfmiddlewaretoken"] = self.csrf_token or ""
            headers["Referer"] = self.base_url
        return self.session.post(self.base_url + path, data=payload, headers=headers, **kw)

    def post_raw(self, path, body, csrf=True, **kw):
        kw.setdefault("timeout", 30)
        headers = dict(kw.pop("headers", {}))
        headers.setdefault("Content-Type", "application/json")
        if csrf:
            headers["X-CSRFToken"] = self.csrf_token or ""
            headers["Referer"] = self.base_url
        return self.session.post(self.base_url + path, data=body, headers=headers, **kw)


@pytest.fixture(scope="session")
def http(base_url):
    return Client(base_url)


@pytest.fixture
def anon(base_url):
    """A bare session with no CSRF token — for checking CSRF is enforced."""
    return requests.Session()


def skip_if_rate_limited(response, what):
    """Turn a 429 into a visible SKIP, never into a silent pass."""
    if response.status_code == 429:
        pytest.skip(f"{what}: {RATE_LIMITED_NOTE}")


def require_write_tests():
    if os.environ.get("RUN_WRITE_TESTS") != "1":
        pytest.skip("write test: set RUN_WRITE_TESTS=1 (complaint POST is capped at 3/hour per IP)")
