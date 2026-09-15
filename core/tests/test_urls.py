"""URL resolution tests for the Bhaktapur Municipal AI project.

Tests that every named URL pattern resolves and returns an expected status
code (200 or 302 for unauthenticated GET requests where applicable).
"""
from django.test import TestCase
from django.urls import resolve, reverse, get_resolver, URLPattern, URLResolver

# Routes that require POST, auth, or specific args — tested separately or skipped
SKIP_PATTERNS = {
    'admin:',           # Django admin — requires staff
    'social:',          # social-auth — requires OAuth provider
    'password_reset_confirm',  # needs uidb64/token args
    'password_reset_done',
    'password_reset_complete',
    'verify_email',
    'resend_verification',
    'totp_setup',       # needs login
    'totp_verify',
    'totp_disable',
    'orders',           # needs auth
    'citizen_dashboard', # needs auth
    'project_follow',   # POST only
    'announcement_comment', # POST only
    'api_search_suggest',  # API endpoint
    'api_map_pins',        # API endpoint
}

# Routes known to 200 for unauthenticated GET
KNOWN_GOOD_ROUTES = {
    '/': 200,
    '/transparency/': 200,
    '/announcements/': 200,
    '/ward-projects/': 200,
    '/ward/1/': 200,
    '/sw.js': 200,
    '/manifest.json': 200,
    '/robots.txt': 200,
    '/favicon.ico': 301,
    '/offline/': 200,
}


def _walk_patterns(patterns, namespace='', prefix=''):
    """Recursively walk URL patterns yielding (pattern_string, name) tuples."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            ns = pattern.namespace or namespace
            new_prefix = prefix + str(pattern.pattern)
            _walk_patterns(pattern.url_patterns, ns, new_prefix)
        elif isinstance(pattern, URLPattern):
            name = pattern.name or ''
            if namespace and name:
                name = f'{namespace}:{name}'
            # Build the raw pattern string (may include <...> args)
            pattern_str = prefix + str(pattern.pattern)
            yield pattern_str, name


class URLResolutionTests(TestCase):
    """Comprehensive URL resolution tests."""

    def test_all_named_urls_resolve(self):
        """Confirm all named URL patterns resolve to a view callable."""
        resolver = get_resolver()
        failures = []

        for pattern_str, name in _walk_patterns(resolver.url_patterns):
            if not name:
                continue
            if any(skip in name for skip in SKIP_PATTERNS):
                continue
            if '<' in pattern_str:
                continue  # needs args, tested separately

            # Normalize pattern: strip leading ^ and trailing $
            path = pattern_str.lstrip('^').rstrip('$')
            if not path.startswith('/'):
                path = '/' + path

            try:
                resolved_func, resolved_args, resolved_kwargs = resolve(path)
                self.assertIsNotNone(resolved_func, f'Resolver returned None for {name} at {path}')
            except Exception as e:
                failures.append((name, path, str(e)))

        self.assertEqual(
            failures, [],
            f'URL resolution failures: {failures}'
        )

    def test_known_routes_return_200_or_302(self):
        """Test that specific known routes return 200 or 302 for unauthenticated GET."""
        failures = []
        for path, expected_code in KNOWN_GOOD_ROUTES.items():
            resp = self.client.get(path)
            if resp.status_code not in (expected_code, 302):
                failures.append((path, expected_code, resp.status_code))
        self.assertEqual(failures, [], f'Route failures: {failures}')

    def test_specific_bug_report_routes(self):
        """Explicit test for the routes mentioned in the bug report."""
        routes = {
            '/transparency/': 200,
            '/announcements/': 200,
            '/ward-projects/': 200,
            '/ward/1/': 200,
        }
        for path, expected in routes.items():
            resp = self.client.get(path)
            self.assertIn(
                resp.status_code, (expected, 302),
                f'{path} returned {resp.status_code}, expected {expected} or 302'
            )

    def test_service_worker_headers(self):
        """Assert /sw.js returns correct Content-Type headers."""
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)
        content_type = resp.get('Content-Type', '')
        self.assertIn('javascript', content_type)

    def test_favicon_exists(self):
        """Assert favicon route does not 404."""
        resp = self.client.get('/favicon.ico')
        self.assertNotEqual(resp.status_code, 404)

    def test_manifest_json(self):
        """Assert manifest.json is served correctly."""
        resp = self.client.get('/manifest.json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('json', resp.get('Content-Type', ''))

    def test_robots_txt(self):
        """Assert robots.txt is served."""
        resp = self.client.get('/robots.txt')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/plain', resp.get('Content-Type', ''))

    def test_offline_page(self):
        """Assert /offline/ loads."""
        resp = self.client.get('/offline/')
        self.assertEqual(resp.status_code, 200)

    def test_homepage_redirects_for_unauthenticated(self):
        """Homepage should 200 for anyone."""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_forgot_password_route(self):
        """Assert forgot-password resolves correctly."""
        resp = self.client.get('/forgot-password/')
        self.assertEqual(resp.status_code, 200)

    def test_named_url_reverse(self):
        """Test reverse() for key named URLs."""
        url_names = [
            'core:home',
            'core:transparency_dashboard',
            'core:announcements_public',
            'core:ward_projects_public',
            'core:robots_txt',
            'core:web_manifest',
            'core:offline',
            'accounts:login',
            'accounts:register',
            'accounts:password_reset',
        ]
        for name in url_names:
            try:
                path = reverse(name)
                self.assertTrue(path.startswith('/'), f'{name} reversed to {path}')
                resp = self.client.get(path)
                self.assertIn(resp.status_code, (200, 302),
                              f'{name} -> {path} returned {resp.status_code}')
            except Exception as e:
                self.fail(f'Failed to reverse {name}: {e}')


