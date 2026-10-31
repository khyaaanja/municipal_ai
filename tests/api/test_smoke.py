"""
API smoke tests for municipal_ai.

Every route below was resolved against the real URLConf before it was written.
This app is server-rendered Django, not a REST API — there is no /api/complaints/
or /api/businesses/. The JSON surface is small and specific:

    /api/chat/              POST   chatbot.views.chat_api
    /api/chat/stream/       POST   chatbot.views.chat_stream
    /api/scan/              POST   core.views.scan_api
    /api/search/suggest/    GET    core.views.search_suggest_api
    /api/map/pins/          GET    core.views.map_pins_api

Everything else a citizen touches is an HTML page, so the HTML routes are
smoke-tested as HTML: status, content type, and a marker that proves the
template actually rendered rather than returning an empty 200.

Run with: pytest tests/api/test_smoke.py -v
Opt-in groups:
    RUN_WRITE_TESTS=1        also submit a real complaint (3/hour per IP)
    EXPECT_PROD_HARDENING=1  also assert DEBUG-page leakage is off
"""
import os
import re

import pytest

from conftest import require_write_tests, skip_if_rate_limited


# --------------------------------------------------------------------------
# Public HTML pages — (path, marker that proves the template rendered)
# --------------------------------------------------------------------------
PUBLIC_PAGES = [
    ("/",                  "bhaktapur"),
    ("/complaint/",        "category"),
    ("/complaint/track/",  "complaint"),
    ("/businesses/",       "business"),
    ("/attractions/",      "attraction"),
    ("/events/",           "event"),
    ("/news/",             "news"),
    ("/marketplace/",      "marketplace"),
    ("/civic/proposals/",  "proposal"),
    ("/civic/polls/",      "poll"),
    ("/civic/petitions/",  "petition"),
    ("/civic/meetings/",   "meeting"),
    ("/services/",         "service"),
    ("/services/notices/", "notice"),
    ("/transparency/",     "complaint"),
    ("/ward-projects/",    "ward"),
    ("/announcements/",    "announcement"),
    ("/search/",           "search"),
    ("/map/",              "map"),
    ("/chat/",             "chat"),
]

# Pages that must NOT be readable by an anonymous visitor.
PRIVATE_PAGES = ["/orders/", "/my/", "/dashboard/", "/services/my/", "/complaint/my/"]


class TestPublicPages:
    """A citizen-facing page that 404s or renders empty is a real outage."""

    @pytest.mark.parametrize("path,marker", PUBLIC_PAGES, ids=[p for p, _ in PUBLIC_PAGES])
    def test_page_renders(self, http, path, marker):
        r = http.get(path)
        assert r.status_code == 200, f"{path} returned {r.status_code}, expected 200"
        assert "text/html" in r.headers.get("Content-Type", ""), f"{path} did not return HTML"
        assert marker in r.text.lower(), (
            f"{path} returned 200 but the page body has no '{marker}' — "
            "template likely rendered empty or wrong"
        )

    def test_unknown_route_is_404(self, http):
        r = http.get("/no-such-page-xyzzy/")
        assert r.status_code == 404, f"Unknown route returned {r.status_code}, expected 404"


class TestAccessControl:
    """These pages hold citizen-specific data. Anonymous access must redirect."""

    @pytest.mark.parametrize("path", PRIVATE_PAGES)
    def test_requires_login(self, http, path):
        r = http.get(path, allow_redirects=False)
        assert r.status_code in (301, 302), (
            f"{path} returned {r.status_code} to an anonymous visitor — "
            "expected a redirect to login. Private data may be publicly readable."
        )
        location = r.headers.get("Location", "")
        assert "/login/" in location, f"{path} redirected to {location!r}, expected the login page"


class TestChatAPI:
    """The chatbot is the app's headline feature and has broken silently before."""

    def test_rejects_post_without_csrf(self, anon, base_url):
        r = anon.post(f"{base_url}/api/chat/", json={"message": "hello"}, timeout=30)
        assert r.status_code == 403, (
            f"POST /api/chat/ without a CSRF token returned {r.status_code}, expected 403. "
            "CSRF protection may have been removed."
        )

    def test_rejects_get(self, http):
        r = http.get("/api/chat/")
        assert r.status_code == 405, f"GET /api/chat/ returned {r.status_code}, expected 405"

    def test_empty_message_rejected(self, http):
        r = http.post_json("/api/chat/", {"message": "   "})
        skip_if_rate_limited(r, "/api/chat/")
        assert r.status_code == 400, f"Empty message returned {r.status_code}, expected 400"
        assert "error" in r.json()

    def test_missing_message_key_rejected(self, http):
        r = http.post_json("/api/chat/", {})
        skip_if_rate_limited(r, "/api/chat/")
        assert r.status_code == 400, f"Missing 'message' returned {r.status_code}, expected 400"

    def test_overlong_message_rejected(self, http):
        r = http.post_json("/api/chat/", {"message": "a" * 1001})
        skip_if_rate_limited(r, "/api/chat/")
        assert r.status_code == 400, f"1001-char message returned {r.status_code}, expected 400"

    def test_malformed_body_rejected(self, http):
        r = http.post_raw("/api/chat/", "{not json")
        skip_if_rate_limited(r, "/api/chat/")
        assert r.status_code == 400, f"Malformed JSON returned {r.status_code}, expected 400"

    def test_answers_a_municipal_question(self, http):
        r = http.post_json("/api/chat/", {"message": "How do I file a complaint about a broken road?"})
        skip_if_rate_limited(r, "/api/chat/")
        assert r.status_code == 200, f"Chat returned {r.status_code}, expected 200"

        data = r.json()
        for key in ("response", "intent", "sources", "followups"):
            assert key in data, f"Chat response is missing the '{key}' key: got {sorted(data)}"
        assert isinstance(data["sources"], list)

        answer = (data["response"] or "").strip()
        assert answer, "Chat returned an empty answer — check GROQ_API_KEY and the answer engine"
        # Fallback guard: the keyword-matcher path has shipped in place of a real
        # answer before, and it produces stub-length replies.
        assert len(answer.split()) >= 15, (
            f"Answer was only {len(answer.split())} words — suspect the keyword "
            f"fallback rather than a real answer: {answer[:120]!r}"
        )

    def test_answers_a_nepali_question(self, http):
        r = http.post_json("/api/chat/", {"message": "भक्तपुर नगरपालिकाको कार्यालय समय के हो?"})
        skip_if_rate_limited(r, "/api/chat/")
        assert r.status_code == 200, f"Nepali query returned {r.status_code}, expected 200"
        answer = (r.json().get("response") or "").strip()
        assert answer, "Nepali query returned an empty answer — bilingual retrieval may be broken"


class TestSearchSuggestAPI:
    def test_short_query_returns_empty_results(self, http):
        r = http.get("/api/search/suggest/?q=a")
        assert r.status_code == 200, f"Returned {r.status_code}, expected 200"
        assert r.json() == {"results": []}, "Queries under 2 chars must return no suggestions"

    def test_missing_query_returns_empty_results(self, http):
        r = http.get("/api/search/suggest/")
        assert r.status_code == 200
        assert r.json() == {"results": []}

    def test_suggestions_have_the_expected_shape(self, http):
        r = http.get("/api/search/suggest/?q=bha")
        assert r.status_code == 200
        results = r.json()["results"]
        assert isinstance(results, list), "'results' must be a list"
        # Non-empty guard: "bha" matches Bhaktapur Durbar Square and friends. An
        # empty list here means the search index or the data behind it is gone —
        # the Sep 15 database loss looked exactly like this.
        assert results, (
            "'bha' returned no suggestions — attraction/business data may be missing"
        )
        for item in results:
            assert set(item) >= {"type", "label", "url"}, f"Suggestion missing keys: {item}"
            assert item["url"].startswith("/"), f"Suggestion url must be a site path: {item['url']!r}"


class TestMapPinsAPI:
    def test_pins_have_usable_coordinates(self, http):
        r = http.get("/api/map/pins/")
        assert r.status_code == 200, f"Returned {r.status_code}, expected 200"

        pins = r.json()["pins"]
        assert isinstance(pins, list), "'pins' must be a list"
        # Non-empty guard, same reasoning as the search suggestions above: the
        # map silently rendering zero pins is a data outage, not a pass.
        assert pins, "The map returned zero pins — attraction/business data may be missing"
        for pin in pins:
            assert set(pin) >= {"type", "name", "lat", "lng", "url"}, f"Pin missing keys: {sorted(pin)}"
            assert pin["type"] in ("attraction", "business"), f"Unexpected pin type {pin['type']!r}"
            assert isinstance(pin["lat"], float) and isinstance(pin["lng"], float), (
                f"Pin {pin['name']!r} has non-float coordinates — the map will not plot it"
            )
            # Bhaktapur sits near 27.67 N, 85.43 E. A pin outside Nepal is bad data.
            assert 26.0 < pin["lat"] < 31.0, f"Pin {pin['name']!r} latitude {pin['lat']} is outside Nepal"
            assert 80.0 < pin["lng"] < 89.0, f"Pin {pin['name']!r} longitude {pin['lng']} is outside Nepal"


@pytest.mark.quota
class TestScanAPI:
    """Validation only — no real image, so this never spends a Groq vision call."""

    def test_rejects_get(self, http):
        r = http.get("/api/scan/")
        assert r.status_code == 405, f"GET /api/scan/ returned {r.status_code}, expected 405"

    def test_malformed_body_rejected(self, http):
        r = http.post_raw("/api/scan/", "{nope")
        skip_if_rate_limited(r, "/api/scan/")
        assert r.status_code == 400, f"Malformed JSON returned {r.status_code}, expected 400"

    def test_missing_image_rejected(self, http):
        r = http.post_json("/api/scan/", {"question": "what is this"})
        skip_if_rate_limited(r, "/api/scan/")
        assert r.status_code == 400, f"Missing image returned {r.status_code}, expected 400"

    def test_corrupt_image_rejected(self, http):
        r = http.post_json("/api/scan/", {"image": "data:image/png;base64,####not-base64####"})
        skip_if_rate_limited(r, "/api/scan/")
        assert r.status_code == 400, f"Corrupt base64 returned {r.status_code}, expected 400"


class TestComplaintForm:
    """Read-only contract check on the form itself — costs no submission quota."""

    REQUIRED_FIELDS = ["category", "title", "description", "ward_number", "name", "csrfmiddlewaretoken"]

    def test_form_exposes_every_required_field(self, http):
        html = http.get("/complaint/").text
        present = set(re.findall(r'name="([a-z_]+)"', html))
        missing = [f for f in self.REQUIRED_FIELDS if f not in present]
        assert not missing, f"Complaint form is missing input(s): {missing}"

    def test_tracking_page_handles_an_unknown_id(self, http):
        r = http.post_form("/complaint/track/", {"complaint_id": "BK-00000000"})
        assert r.status_code == 200, f"Tracking an unknown ID returned {r.status_code}, expected 200"
        assert "no complaint found" in r.text.lower(), (
            "Unknown complaint ID did not produce a 'not found' message"
        )


@pytest.mark.write
class TestComplaintSubmission:
    """Opt-in: the submit endpoint allows only 3 POSTs per hour per IP."""

    def test_invalid_submission_is_rejected_not_crashed(self, http):
        require_write_tests()
        r = http.post_form("/complaint/", {"category": "", "title": "", "description": ""})
        assert r.status_code == 200, f"Empty submission returned {r.status_code}, expected a re-rendered form"
        assert "BK-" not in r.text, "An empty complaint was accepted and given a tracking ID"

    def test_valid_submission_returns_a_bk_tracking_id(self, http):
        require_write_tests()
        r = http.post_form("/complaint/", {
            "category": "SANITATION",
            "title": "QA smoke test — please ignore",
            "description": "Automated smoke test submission from tests/api/test_smoke.py",
            "location": "Durbar Square",
            "ward_number": "5",
            "name": "QA Bot",
            "email": "qa@example.com",
            "priority": "LOW",
        }, allow_redirects=True)
        if "too many submissions" in r.text.lower():
            pytest.skip("complaint submission: hourly quota of 3/IP already spent, not a defect")
        assert r.status_code == 200, f"Valid submission returned {r.status_code}"
        assert re.search(r"BK-[A-Z0-9]+", r.text), (
            "Valid complaint did not produce a BK- tracking ID on the success page"
        )


class TestSecretsNotExposed:
    """No configured secret may appear in a page an anonymous visitor can fetch."""

    SECRET_VARS = [
        "SECRET_KEY", "GROQ_API_KEY", "KHALTI_SECRET_KEY",
        "GOOGLE_OAUTH2_SECRET", "TOTP_ENCRYPTION_KEY", "DB_PASSWORD",
    ]

    @staticmethod
    def _configured_secrets():
        """Read .env values locally so we can search for them. Values are never
        printed — failures name the variable only."""
        secrets = {}
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        if not os.path.exists(env_path):
            return secrets
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                if "=" not in line or line.lstrip().startswith("#"):
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                # Skip short/placeholder values — they cause false positives.
                if key in TestSecretsNotExposed.SECRET_VARS and len(value) >= 12:
                    secrets[key] = value
        return secrets

    def test_no_secret_appears_in_public_html(self, http):
        secrets = self._configured_secrets()
        if not secrets:
            pytest.skip("no .env secrets long enough to check on this host")
        for path, _ in PUBLIC_PAGES:
            body = http.get(path).text
            for name, value in secrets.items():
                assert value not in body, f"{name} is exposed in the HTML of {path}"

    def test_no_secret_appears_in_json_endpoints(self, http):
        secrets = self._configured_secrets()
        if not secrets:
            pytest.skip("no .env secrets long enough to check on this host")
        for path in ("/api/map/pins/", "/api/search/suggest/?q=bha", "/manifest.json"):
            body = http.get(path).text
            for name, value in secrets.items():
                assert value not in body, f"{name} is exposed in the response from {path}"


@pytest.mark.hardening
class TestProductionHardening:
    """Set EXPECT_PROD_HARDENING=1 when pointing this suite at a public URL.

    Skipped by default because DEBUG=True is normal on a dev box. It is not
    normal on the ngrok URL citizens can reach — that leak was filed on Sep 16.
    """

    @staticmethod
    def _require_opt_in():
        if os.environ.get("EXPECT_PROD_HARDENING") != "1":
            pytest.skip("production-hardening check: set EXPECT_PROD_HARDENING=1 when testing a public URL")

    def test_404_does_not_leak_the_urlconf(self, http):
        self._require_opt_in()
        body = http.get("/no-such-page-xyzzy/").text
        assert "Using the URLconf defined in" not in body, (
            "DEBUG is on: the 404 page is publishing the full URL pattern list"
        )

    def test_error_pages_do_not_announce_debug_mode(self, http):
        self._require_opt_in()
        body = http.get("/no-such-page-xyzzy/").text.lower()
        # Markers verified to appear on Django's DEBUG 404 page. "traceback" and
        # "exception value" only show on 500s, so asserting those here would
        # pass whether DEBUG was on or off — a test that cannot fail.
        for token in ("debug = true", "seeing this error because"):
            assert token not in body, (
                f"DEBUG is on: the error page publishes {token!r} to anonymous visitors"
            )
