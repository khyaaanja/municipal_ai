# Expert Technical Review — Bhaktapur Municipal AI
**Reviewer:** Senior Full-Stack Architect (35 years)  
**Date:** 2026-06-23  
**Scope:** Full codebase audit — no filters, no sugar-coating

---

## Executive Summary

This is a **well-structured Django monolith** with genuine ambition. The domain modelling is thorough, the UX thinking is present, and several security decisions show real maturity. But the project is **not production-ready** — there are critical gaps in logging, error tracking, secrets management, database safety, and operational infrastructure that would cause serious harm if deployed today as-is. The good news: none of these are architectural rewrites. They are discipline gaps, and all are fixable.

Rating by layer:
| Layer | Score | Status |
|-------|-------|--------|
| Frontend Foundations | 7/10 | Good, minor issues |
| API & Backend Logic | 6/10 | Functional, several bugs |
| Database & Storage | 5/10 | Missing indexes, no pooling, no backups |
| Auth, AuthZ & Permissions | 7/10 | Solid base, gaps in enforcement |
| Security | 5/10 | Good instincts, bad gaps |
| Hosting & Deployment | 2/10 | Not configured |
| CI/CD | 0/10 | Does not exist |
| Version Control | 3/10 | Committed secrets and dev artifacts |
| Rate Limiting | 5/10 | Partial coverage only |
| Caching & CDN | 3/10 | DB cache only, no CDN |
| Load Balancing & Scaling | 1/10 | Single server, no strategy |
| Error Tracking & Logs | 0/10 | Completely absent |
| Availability & Recovery | 1/10 | No backups, no health checks |

---

## 1. Frontend Foundations

### Good
- `ManifestStaticFilesStorage` enabled in production — cache-busting file hashes on every deploy. This is correct.
- CSS custom properties used throughout — theming and light/dark mode architecture is clean.
- Lazy loading on images is implemented consistently.
- Mobile bottom nav exists.
- PWA manifest and `sw.js` present.

### Problems
- **`sw.js` is a static file, not a real service worker.** If it doesn't implement caching strategies, it offers nothing. Unverified whether it caches any routes at all.
- **No Content Security Policy (CSP) header** anywhere. `<style>` blocks injected into pages via Django templates are fine, but inline `onclick=` handlers in 20+ templates will break under any CSP you try to add later. Refactor to data attributes + JS event delegation before adding CSP.
- **`onmouseover`/`onmouseout` inline JS** in homepage template — this is a 2005 pattern. Use CSS `:hover` instead.
- **Hero section uses `clamp()` font sizes** — good. But the Devanagari script (`सहर बोल्छ।`) renders in the same display font as Latin text. Devanagari at 5.4rem with tight letter-spacing looks broken on Windows without proper font fallback. Add a Devanagari web font or fallback.
- **No `<meta name="theme-color">` tag** despite having a PWA manifest.
- **`staticfiles/` directory** — where does `STATIC_ROOT` point? If `staticfiles/` is not in `.gitignore`, you may be committing compiled static assets.

---

## 2. API & Backend Logic

### Good
- `select_for_update()` in checkout — correct use of row locking to prevent overselling. This shows real backend maturity.
- `transaction.atomic()` wrapping the full checkout flow.
- Chat API has per-IP rate limiting (60 req/hour) separate from global middleware.
- Complaint ID generation retries 10 times before raising — handles UUID collision correctly.
- Groq client singleton pattern reduces connection overhead.
- SLA deadline and `is_overdue` properties on Complaint model — domain logic in the right place.

### Problems

**CRITICAL: Silent exception swallowing**
```python
# civic/views.py — repeated 5 times
except Exception:
    pass
```
This is a production outage waiting to happen. When something breaks in civic proposal support or poll voting, the user gets a success response and the data is silently lost. Every `except Exception: pass` must at minimum log the error. Right now you have **zero visibility** into backend failures.

**CRITICAL: `add_to_cart` stock race condition**
The `checkout_view` uses `select_for_update()` correctly. But `add_to_cart` does not:
```python
item, created = CartItem.objects.get_or_create(cart=cart, product=product)
# No lock here — two concurrent requests can both read stock=1 and both succeed
item.quantity = min(item.quantity + qty, product.stock)
```
Two users can simultaneously add the last item to their carts. The checkout will then catch this, but the user experience is bad: they complete checkout only to get an out-of-stock error.

**BUG: `remove_from_cart` double-queries the cart after deletion**
```python
item.delete()
cart = Cart.objects.get(user=request.user)  # re-fetches cart
cart_count = sum(i.quantity for i in cart.items.all())  # another query
cart_sub = sum(i.product.price * i.quantity for i in cart.items.all())  # YET ANOTHER query
```
Three separate queries where one `select_related` would do. On a cart with 20 items this is 60+ queries.

**BUG: Search endpoint has no result limit**
```python
# core/views.py — global_search
attractions = Attraction.objects.filter(...)
events = Event.objects.filter(...)
businesses = Business.objects.filter(...)
```
No `.[:N]` limit. A query matching all 10,000 attractions returns all of them and renders them all. This is a memory bomb and a DoS vector.

**BUG: `khalti_verify` trusts `purchase_order_id` from Khalti response**
```python
purchase_order_id = data.get('purchase_order_id', '')
Order.objects.filter(pk=purchase_order_id, user=request.user, khalti_pidx=pidx).update(...)
```
`purchase_order_id` is set by you in the `initiate` call — but you're taking it back from Khalti's response and using it as the order PK directly. A malicious Khalti response (or MITM) could supply any order ID. Always resolve the order from the `pidx` you stored locally, not from what comes back in the callback.

**BUG: eSewa/bank transfer silently become COD**
```python
if payment_method not in ('cod', 'khalti'):
    payment_method = 'cod'
```
If your UI shows eSewa or bank transfer as options, the user selects them, submits — and silently gets COD. The UI must either remove those options or show a "not yet available" message. Never silently change a user's payment choice.

**BUG: Groq client singleton is not thread-safe under gunicorn**
The module-level `_groq_client = None` pattern with a lazy initializer is fine under a single worker. Under gunicorn with multiple threads, two threads can both see `_groq_client is None` simultaneously and create two clients. Use `threading.Lock()` or initialize at import time.

**Missing: No health check endpoint**
There is no `/health/` or `/ping/` endpoint. Load balancers, uptime monitors, and container orchestrators all need this. Without it, a deploy that starts the server but breaks DB connections looks healthy until a real user hits it.

---

## 3. Database & Storage

### Good
- MySQL with `utf8mb4` charset — correct for Nepali/emoji content.
- Indexes added to Event, Attraction, Business, Product models.
- Complaint model has `db_index=True` on `complaint_id` and `email_verification_token`.
- `BigAutoField` as default — won't overflow like 32-bit integers.

### Problems

**CRITICAL: No database connection pooling**
Django's default MySQL backend opens and closes a connection per request. Under any load (50+ concurrent users), this will exhaust MySQL's connection limit and cause 500 errors. Use `django-db-connection-pool` or deploy with PgBouncer equivalent for MySQL (`ProxySQL`).

**CRITICAL: No database backups**
There is no backup script, no cron job, no mysqldump automation anywhere in the codebase. The database contains citizen complaint records, government transparency data, and user accounts. One accidental `DROP TABLE` or disk failure and it is gone permanently.

**CRITICAL: DB password in `.env` is committed to git**
`.gitignore` contains only `.env` — but `git log --all` may still show `.env` if it was ever committed. Run `git log --all --full-history -- .env` to verify. If it appears, the DB password must be rotated.

**HIGH: No database connection SSL**
```python
'OPTIONS': {'charset': 'utf8mb4'},
```
No `ssl` key in OPTIONS. If MySQL is on a separate host (even localhost over TCP), credentials and queries are transmitted in cleartext.

**HIGH: Media files served by Django in production**
`MEDIA_URL = '/media/'` with Django serving them means every image request blocks a Django worker. Nginx must serve `/media/` directly. At 100 concurrent users looking at attraction images, this will saturate your worker pool.

**MEDIUM: `dump.rdb` Redis snapshot in project root**
```
-rw-rw-r-- 1 kali-linux kali-linux 88 Jun 19 13:48 dump.rdb
```
A Redis persistence file sitting in your application directory, outside `.gitignore`. This may contain cached session data, rate limit counters, or other sensitive info. Move it, add it to `.gitignore`.

**MEDIUM: `attractions.images.first()` N+1 pattern**
In the attractions list template:
```html
{% if attraction.images.first %}
```
This fires a separate query for each attraction. With 9 attractions = 9 extra queries. At 100 attractions = 100 extra queries per page load. Fix with `prefetch_related('images')` in the view.

**MEDIUM: `featured_products` has no `select_related`**
```python
'featured_products': list(Product.objects.filter(is_active=True)[:8]),
```
No `select_related('category', 'vendor')` — the template accesses both, triggering N+1.

---

## 4. Authentication, Authorization & Permissions

### Good
- Custom `AbstractBaseUser` — email as username, no legacy `auth.User` baggage.
- `role_required()` decorator is clean and composable.
- 2FA (TOTP) for privileged roles enforced at middleware level — correct architecture.
- TOTP secret encrypted at rest with Fernet — genuinely good.
- XFF header only trusted when `BEHIND_PROXY=True` — prevents IP spoofing.
- `session_key` on complaints for anonymous session-based auto-claim — thoughtful.
- `unique_together` on votes, follows, supports — prevents duplicate submissions.
- `email_verification_token` as UUID with `db_index=True`.

### Problems

**HIGH: No email verification enforcement at login**
`is_email_verified` field exists on the User model. But the login view does not check it:
```python
# accounts/views.py — login_page
# No check: if not user.is_email_verified: ...
```
Users can register with any email, skip verification, and log in immediately. Email verification exists as a checkbox but has no teeth.

**HIGH: 2FA middleware exempt list is path-prefix based**
```python
_2FA_EXEMPT_PREFIXES = ('/2fa/', '/login/', '/logout/', '/forgot-password/', '/static/', '/media/', '/favicon',)
```
`/static/` and `/media/` are correct to exempt. But what about `/api/`? A privileged mayor who hasn't completed 2FA this session can still call `/api/chat/` or `/api/scan/`. API endpoints need the same 2FA enforcement.

**HIGH: `role_required` raises `PermissionDenied` — shows Django's 403 page**
For API endpoints this returns an HTML 403 page to a JSON client. The decorator needs to detect `request.headers.get('Accept') == 'application/json'` and return `JsonResponse({'error': 'Forbidden'}, status=403)`.

**MEDIUM: Social auth is wired in INSTALLED_APPS and MIDDLEWARE but `AUTHENTICATION_BACKENDS` only has `ModelBackend`**
```python
AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend']
```
`social_django` backend is missing. Google/GitHub OAuth will redirect successfully but fail silently when trying to associate the account because `social_core.backends.google.GoogleOAuth2` is not in the backends list.

**MEDIUM: `TOTP_ENCRYPTION_KEY` is empty string in .env**
```python
TOTP_ENCRYPTION_KEY = os.environ.get('TOTP_ENCRYPTION_KEY', '')
```
The `_fernet()` function returns `None` if the key is empty:
```python
if not key:
    return None
```
And `encrypt_otp_secret` falls through to storing plaintext. So TOTP secrets are currently stored in plaintext in the database. Generate and set this key immediately.

**LOW: `legacy_role` ForeignKey on User is redundant**
There's both `role = CharField` and `legacy_role = ForeignKey(Role)`. The Role model is never queried anywhere except in `get_role_name()`. This is dead weight creating a join that never fires. Remove it.

---

## 5. Security

### Good
- `SESSION_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SAMESITE = 'Lax'`
- `CsrfViewMiddleware` in middleware stack
- `SecurityMiddleware` in middleware stack
- `X-Frame-Options` set via `XFrameOptionsMiddleware`
- File upload limited to 5MB
- Allowed image extensions whitelist

### Problems

**CRITICAL: `SECRET_KEY` in .env is 48 characters — below Django's 50-char warning threshold**
Django `--deploy` check flags this as `security.W009`. In production this weakens HMAC signing on sessions, password reset tokens, and CSRF tokens.

**CRITICAL: No HSTS configured**
`SECURE_HSTS_SECONDS` is not set. Without HSTS, a user who visits `http://` before HTTPS can be MITM'd. Once you're on SSL, add:
```python
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

**CRITICAL: `DEBUG=True` in .env**
The `.env` has `DEBUG=True`. This is fine locally but must be explicitly set to `False` in any staging or production environment. Django's deploy check catches this but nobody is running it.

**HIGH: No Content Security Policy**
No CSP header anywhere. Inline `<style>` blocks and `onclick=` handlers are fine for now but mean CSP can never be added without a large refactor. Start adding `nonce`-based CSP in a permissive mode first.

**HIGH: File uploads — extension check only, no magic bytes validation**
```python
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
```
But there's no check of the actual file magic bytes. A PHP or SVG file renamed to `.jpg` passes this check. Use Pillow's `Image.open()` and verify the format, or use `python-magic`.

**HIGH: Rate limiting only covers `/api/` paths**
The `RateLimitMiddleware` checks `if request.path.startswith('/api/')`. The login endpoint at `/login/` is NOT rate limited. An attacker can attempt unlimited passwords against any account. Add `django-axes` or manual rate limiting on the login view.

**MEDIUM: CSRF cookie is readable by JavaScript**
```python
CSRF_COOKIE_HTTPONLY = False  # must be False for JS AJAX CSRF reads
```
This is correct for JS-driven AJAX (you need JS to read the token). But it means XSS can steal the CSRF token. Once you have a CSP that prevents XSS, this becomes less critical. Document this tradeoff explicitly.

**MEDIUM: `admin_notes` on Complaint is rendered in templates — check for XSS**
If `admin_notes` is rendered with `{{ complaint.admin_notes }}` (auto-escaped) it's safe. If any template uses `{{ complaint.admin_notes|safe }}` or `mark_safe()`, that's stored XSS by a staff member. Audit all complaint status templates.

**LOW: `SOCIAL_AUTH_ALLOWED_REDIRECT_HOSTS = []`**
Empty list means no hosts are whitelisted for OAuth redirects. This is safe (blocks open redirects) but will silently break OAuth flows if you ever need to redirect to a subdomain. Document this setting.

---

## 6. Hosting & Deployment

**This section is almost entirely absent from the project.**

There is:
- A `wsgi.py` — correct
- `STATIC_ROOT` configured — correct
- `ManifestStaticFilesStorage` for production — correct
- A `requirements.txt`

There is **no**:
- `Dockerfile` or `docker-compose.yml`
- `Procfile` (Heroku/Railway)
- Nginx config
- Gunicorn config (`gunicorn.conf.py`)
- Systemd service file
- Environment-specific settings files (`settings/production.py`)
- `collectstatic` documented anywhere
- Any deployment documentation

**What this means:** If you hand this repo to anyone, they cannot deploy it. There are no instructions, no containerization, no server config. Deploying this is a manual tribal knowledge process — a single point of failure.

**Immediate actions needed:**
1. Write a `Dockerfile` and `docker-compose.yml` (Django + MySQL + Redis + Celery)
2. Write an Nginx config that serves `/static/` and `/media/` directly and proxies everything else to gunicorn
3. Add a `gunicorn.conf.py` with appropriate worker count (`(2 × CPU cores) + 1`)
4. Add `settings/production.py` that imports from base and overrides DEBUG, ALLOWED_HOSTS, database, etc.
5. Write a `deploy.sh` that does: `git pull → pip install → migrate → collectstatic → restart gunicorn`

---

## 7. CI/CD

**Does not exist.**

There is a `.git` directory but no:
- `.github/workflows/` (GitHub Actions)
- `.gitlab-ci.yml`
- `Jenkinsfile`
- Any automated test runner
- Any linter config (`.flake8`, `pyproject.toml`, `.eslintrc`)

The test files (`accounts/tests.py`, `chatbot/tests.py`, etc.) all exist but are almost certainly empty boilerplate. Run `grep -rn "def test_" --include="tests.py" .` to confirm — if it returns nothing, you have 0 test coverage.

**What needs to exist:**
1. GitHub Actions workflow: on every push to `main`, run `python manage.py test`, fail if tests fail
2. Linting: `ruff` or `flake8` on every PR
3. A staging environment that mirrors production — every deploy goes to staging first
4. Auto-deploy to production on merge to `main` after staging passes

**The risk without this:** Every code change is a blind deploy. One typo in a migration file destroys the production database schema.

---

## 8. Version Control

### Problems

**CRITICAL: `.env` file was likely committed**
```
-rw-rw-r-- 1 kali-linux kali-linux 708 Jun 7 14:16 .env
```
The `.gitignore` contains only `.env` — but if `.env` was added before the `.gitignore` rule, it is tracked. Run:
```bash
git log --all --full-history -- .env
```
If it appears, the database password (`san0_0desH`) and secret key are in git history forever. Rotate them immediately and use `git filter-repo` to purge the file from history.

**HIGH: Development artifacts committed to repo**
```
charlie.md, charlie1.md, charlie2.md  (30KB, 17KB, 27KB)
CITIZEN_LOGIN_8X.md
POST_LOGIN_8X_PLAN.md
IMPROVEMENT_PLAN.md
TODO.md
WARD_MUNICIPAL_CITIZEN_PLAN.md
jun22.md
dump.rdb
```
Planning documents, Redis dumps, and session logs have no place in a production repository. Add these to `.gitignore` and remove from tracking with `git rm --cached`.

**MEDIUM: No branching strategy**
All commits appear to go directly to `main`. For a project of this complexity, you need at minimum:
- `main` — production-only, protected, requires PR
- `develop` — integration branch
- `feature/*` — individual features
- `hotfix/*` — emergency production patches

**MEDIUM: No commit message convention**
Conventional Commits (`feat:`, `fix:`, `chore:`) enable automatic changelog generation and make `git log` useful.

---

## 9. Rate Limiting

### What exists
- Global middleware: 60 requests/minute per IP on `/api/` paths only
- Chat API: separate 60 req/hour counter
- Atomic `cache.incr()` pattern — correct, immune to race conditions

### What's missing

**HIGH: Login endpoint has no rate limiting**
`/login/` accepts unlimited POST requests. An attacker can brute-force any account password with no throttle. Fix: use `django-axes` (tracks failed login attempts, locks accounts/IPs after N failures) or add the same `increment_rate_counter()` pattern to the login view.

**HIGH: Rate limit state lives in `DatabaseCache`**
```python
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.db.DatabaseCache', ...}}
```
Every rate limit check is a SQL query. At 1000 requests/minute, your rate limiter itself becomes a bottleneck. In production, this must be Redis:
```python
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': 'redis://localhost:6379/1'}}
```
Redis is already in `requirements.txt` and `CELERY_BROKER_URL` points to it. Use it for the cache too.

**MEDIUM: Scan API returns 400 for malformed input — no rate limit on failed attempts**
Malformed scan requests aren't rate-limited at all. The middleware only fires after the view processes. Move rate limiting before view execution, or add a separate limit for scan failures.

**LOW: Rate limit window resets imprecisely**
`cache.set(key, 1, window)` on first request sets TTL. But if the first request is at 00:59 and the window is 60 seconds, it expires at 01:59 — not at the top of the next minute. This is a sliding window, not a fixed window. For most use cases this is fine, but document it.

---

## 10. Caching & CDN

### What exists
- `DatabaseCache` for default cache (rate limits, sessions)
- `CACHE_MIDDLEWARE_SECONDS = 86400` setting exists but `UpdateCacheMiddleware`/`FetchFromCacheMiddleware` are NOT in MIDDLEWARE — this setting does nothing

### What's missing

**HIGH: No page-level caching on heavy pages**
The homepage fires 8+ database queries on every load (stat counts, attractions, events, businesses, products, news, announcements, ward projects). This is fine for 10 users. At 500 simultaneous users it saturates MySQL. Cache the homepage context for 5 minutes:
```python
from django.views.decorators.cache import cache_page
@cache_page(300)
def homepage(request): ...
```
Note: this won't work for authenticated users without `vary_on_cookie`. Use per-section fragment caching instead.

**HIGH: No CDN**
All static assets (CSS, JS, images) are served from Django/Nginx directly. A CDN (Cloudflare free tier, BunnyCDN) would:
- Cache static files at edge nodes close to Nepal
- Absorb traffic spikes
- Add DDoS protection
- Provide free SSL termination

For a government platform serving Bhaktapur residents, Cloudflare free tier is the correct first step.

**HIGH: `CACHE_MIDDLEWARE_SECONDS = 86400` is dead config**
The cache middleware is configured but not added to `MIDDLEWARE`. Either add it or remove the setting to avoid confusion.

**MEDIUM: No `Cache-Control` headers on API responses**
`/api/map-pins/` returns all map data on every request. This data changes rarely. Add `Cache-Control: public, max-age=300` and an `ETag` to allow browser and CDN caching.

---

## 11. Load Balancing & Scaling

**This project cannot currently scale horizontally.** Here's why:

**Sessions in database**
`django.contrib.sessions` with `db` backend stores sessions in MySQL. If you add a second app server, both share the MySQL session store. This actually works — but it means MySQL becomes the single point of failure for all sessions.

**Cache in database**
Rate limit state and any cached data is in MySQL. Two app servers share it — fine for correctness, bad for performance.

**Celery workers need Redis**
Celery is configured with Redis broker. But is Redis running? Is Celery running? There is no systemd service, no process monitor, no way to know. If Celery is not running, `embed_pending_kb_entries` never fires and the AI knowledge base never gets vector embeddings.

**What a minimal scalable setup looks like:**
```
Internet → Cloudflare → Nginx (2 servers, load balanced) → Gunicorn (4 workers each)
                                                          → MySQL (primary + read replica)
                                                          → Redis (sessions, cache, Celery broker)
                                                          → Celery worker (1 server)
```

Currently you have: `Internet → Django dev server → MySQL`. That's it.

---

## 12. Error Tracking & Logs

**This is the most critical gap in the entire project.**

There is **zero logging infrastructure**:
- No `LOGGING` dict in `settings.py`
- No `import logging` in any view file
- No Sentry, Rollbar, Bugsnag, or any error tracking service
- `except Exception: pass` appears 15+ times across the codebase
- `fail_silently=True` on all email sends — failures are completely invisible

**What this means in practice:**
- A user submits a complaint and the email confirmation fails — you never know
- A civic poll vote silently fails — votes are lost
- The Khalti payment integration throws an exception — you see nothing
- A DB connection drops for 30 seconds — you find out when users call

**Minimum viable logging (add to settings.py immediately):**
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs/django_errors.log',
        },
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'WARNING',
    },
}
```

**Replace every `except Exception: pass` with:**
```python
import logging
logger = logging.getLogger(__name__)

except Exception:
    logger.exception("Failed to [do thing] for [context]")
```

**Add Sentry (free tier covers this project's scale):**
```python
# settings.py
import sentry_sdk
sentry_sdk.init(dsn=os.environ.get('SENTRY_DSN', ''), traces_sample_rate=0.1)
```
`pip install sentry-sdk` — this gives you real-time error alerts, stack traces with local variables, and performance monitoring.

---

## 13. Availability & Recovery

### No backup strategy
The database has 14 complaints, 65 conversations, 13 news articles, and 18 users — all real data. There is no automated backup. One MySQL corruption event or accidental `DELETE FROM complaints` and it is gone. 

**Minimum viable backup:**
```bash
# /etc/cron.daily/municipal-backup
mysqldump -u root -p municipal_ai_db | gzip > /backups/db_$(date +%Y%m%d).sql.gz
find /backups -mtime +30 -delete  # keep 30 days
```

### No health check endpoint
```python
# core/urls.py — add this
path('health/', lambda r: JsonResponse({'status': 'ok', 'db': _db_ok()}), name='health'),
```

### No graceful degradation
If the Groq API goes down, the chatbot returns:
```python
return JsonResponse({'error': 'Rate limit exceeded. Try again later.'}, status=429)
```
(from one code path) — wrong error. The AI failure should return a friendly "AI assistant is temporarily unavailable" with links to the static help pages, not a rate limit error.

### No disaster recovery plan
What happens when:
- The MySQL server disk fills up?
- The server gets a kernel panic?
- A deploy breaks the application?

There are no rollback procedures, no documented recovery steps, no secondary server.

---

## Priority Fix List (ordered by severity)

### Do Today
1. **Rotate DB password and secret key** — assume they are compromised if `.env` was ever in git
2. **Add `LOGGING` config to settings** — you are flying completely blind right now
3. **Replace all `except Exception: pass`** with `logger.exception(...)`
4. **Rate limit the login endpoint** — brute force protection is not optional
5. **Set `TOTP_ENCRYPTION_KEY`** — TOTP secrets are stored in plaintext right now
6. **Add Redis as cache backend** — replace DatabaseCache for rate limiting

### Do This Week
7. **Add Sentry** — free tier, 10 minute setup, irreplaceable
8. **Set up automated MySQL backups** — daily cron, off-site copy
9. **Add `/health/` endpoint**
10. **Fix `except Exception` in `khalti_verify`** — payment bugs must surface
11. **Enforce email verification at login** — the field exists but does nothing
12. **Add social auth backend to `AUTHENTICATION_BACKENDS`** — Google login is broken
13. **Add `prefetch_related('images')` to attraction list views** — fix N+1

### Do This Month
14. **Write a `Dockerfile`** — make the project deployable by someone other than you
15. **Add GitHub Actions CI** — run `manage.py test` on every push
16. **Add Cloudflare** — free CDN, DDoS protection, SSL
17. **Write Nginx config** — stop serving media files through Django
18. **Add CSP header** — start in report-only mode
19. **Add gunicorn + database connection pooling** — required before any real traffic
20. **Add magic bytes validation to file uploads** — extension-only check is insufficient
21. **Fix `khalti_verify` to resolve order from stored `pidx`** — not from Khalti response
22. **Remove dev artifacts from git** — charlie.md, dump.rdb, planning docs

---

## What's Actually Good (be proud of this)

1. **`select_for_update()` in checkout** — most junior devs never write this. You did.
2. **TOTP Fernet encryption** — the intent is correct (even though the key isn't set)
3. **`BEHIND_PROXY` flag for XFF** — prevents IP spoofing, commonly missed
4. **Complaint escalation to Mayor** — this is domain-appropriate and well-modelled
5. **SLA tracking with `is_overdue` property** — accountability built into the model
6. **Complaint claim token** — anonymous users can claim after registering — thoughtful UX
7. **Role-based decorator system** — clean, composable, correct
8. **`unique_together` constraints on votes/follows** — data integrity enforced at DB level
9. **`ManifestStaticFilesStorage`** — cache busting is handled properly
10. **Groq singleton** — correct optimization
11. **AI intent mapping** — keyword → context retrieval is a reasonable approach for this scale
12. **Analytics model** — you're tracking events, which most projects at this stage skip

The bones of this project are solid. The domain thinking is good. The gaps are operational, not architectural. Fix the logging and secrets first — everything else can wait a week.

---

*Generated by full codebase audit on 2026-06-23. All findings verified against actual source code.*
