import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get('DEBUG', 'False') == 'True'
_DEFAULT_SECRET_KEY = 'bhaktapur-ai-dev-secret-key-change-in-production'
SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = _DEFAULT_SECRET_KEY
    else:
        raise ImproperlyConfigured('SECRET_KEY must be set when DEBUG=False')
if not DEBUG and SECRET_KEY == _DEFAULT_SECRET_KEY:
    raise ImproperlyConfigured('The development SECRET_KEY cannot be used when DEBUG=False')
# Allow common dev/test hosts used by Django's RequestFactory / runserver.
# If ALLOWED_HOSTS env var is not set (common when running via some process managers),
# fall back to .env-style host list including ngrok.
_default_allowed = 'localhost,127.0.0.1,0.0.0.0,testserver'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS')
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = _default_allowed
# Merge in a safe dev host even if ALLOWED_HOSTS is provided via env.
# This prevents DisallowedHost when the app is reachable at http://0.0.0.0:8000.
ALLOWED_HOSTS = str(ALLOWED_HOSTS).split(',')
if '0.0.0.0' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('0.0.0.0')


# Optional extra hosts without needing to edit .env (comma-separated).
_extra_allowed = os.environ.get('EXTRA_ALLOWED_HOSTS', '')
if _extra_allowed.strip():
    ALLOWED_HOSTS += [h.strip() for h in _extra_allowed.split(',') if h.strip()]

# Normalize + de-duplicate, then ensure Django test host is allowed.
ALLOWED_HOSTS = sorted({h.strip() for h in ALLOWED_HOSTS if h and h.strip()})
if 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')







# ── Production security (all inactive when DEBUG=True) ────────────────────────
_IS_PROD = not DEBUG
# Increase from Django's default 2.5MB to allow larger municipal document uploads
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
SECURE_SSL_REDIRECT          = _IS_PROD
# Ensure both settings are respected even when Django globals are loaded
if not _IS_PROD:
    # In development, also set the venv-level override if needed
    pass
SECURE_HSTS_SECONDS          = 31536000 if _IS_PROD else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = _IS_PROD
SECURE_HSTS_PRELOAD          = _IS_PROD
SESSION_COOKIE_SECURE        = _IS_PROD
CSRF_COOKIE_SECURE           = _IS_PROD
SECURE_BROWSER_XSS_FILTER    = True
SECURE_CONTENT_TYPE_NOSNIFF  = True
SECURE_PROXY_SSL_HEADER      = ('HTTP_X_FORWARDED_PROTO', 'https') if _IS_PROD else None
USE_X_FORWARDED_HOST         = _IS_PROD

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    # Project apps
    'accounts',
    'core',
    'chatbot',
    'tourism',
    'marketplace',
    'businesses',
    'events',
    'news',
    'reviews',
    'favorites',
    'itinerary',
    'vendor',
    'adminpanel',
    'mayor',
    'chairperson',
    'civic',
    'services',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.ContentSecurityPolicyMiddleware',
    'core.middleware.RateLimitMiddleware',
    'core.middleware.TwoFactorMiddleware',
]

ROOT_URLCONF = 'municipal_ai.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.global_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'municipal_ai.wsgi.application'

# Database — MySQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'municipal_ai_db'),
        'USER': os.environ.get('DB_USER', 'root'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {'charset': 'utf8mb4'},
        'CONN_MAX_AGE': 60,         # reuse DB connections instead of open/close per request
        'CONN_HEALTH_CHECKS': True, # drop stale connections automatically
    }
}

AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/my/'
LOGOUT_REDIRECT_URL = '/'

# Set True when running behind Nginx/Apache reverse proxy so X-Forwarded-* headers are trustworthy
# (For ngrok deployments, you MUST enable this or Django will see http:// internally.)
BEHIND_PROXY = os.environ.get('BEHIND_PROXY', 'False') == 'True'

# Ensure scheme/host are derived from forwarded headers when behind a proxy.
USE_X_FORWARDED_HOST = BEHIND_PROXY
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if BEHIND_PROXY else None



AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kathmandu'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Production: add versioning hash to static file URLs for long cache TTL
if not DEBUG:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

# Cache-Control for static assets via Django's cache middleware
CACHE_MIDDLEWARE_ALIAS = 'default'
CACHE_MIDDLEWARE_SECONDS = 86400  # 24 hours for page-level caching if used

# Cache — Redis in production, in-memory cache as fallback for dev without Redis
_redis_url = os.environ.get('REDIS_URL', os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/1'))
try:
    import redis as _redis_lib
    _r = _redis_lib.from_url(_redis_url, socket_connect_timeout=1)
    _r.ping()
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _redis_url,
        }
    }
except Exception as _redis_exc:
    # LocMemCache is per-process. In production that silently breaks the
    # chat_async -> chat_poll handshake whenever the poll lands on a different
    # worker than the write, multiplies every rate limit by the worker count,
    # and would do the same to pending-action tokens. Degrading quietly is
    # worse than not starting, so outside DEBUG this is fatal.
    if not DEBUG:
        raise ImproperlyConfigured(
            f'Redis is required when DEBUG=False (tried {_redis_url}): {_redis_exc}'
        )
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'municipal-ai-local-cache',
        }
    }

# Email
_default_email_backend = (
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG else
    'django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_BACKEND       = os.environ.get('EMAIL_BACKEND', _default_email_backend)
EMAIL_HOST          = os.environ.get('EMAIL_HOST',     'smtp.gmail.com')
EMAIL_PORT          = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER',     '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL',  'noreply@bhaktapur.gov.np')
SERVER_EMAIL        = DEFAULT_FROM_EMAIL


# Groq AI API
GROQ_API_KEY          = os.environ.get('GROQ_API_KEY', '')
GROQ_MODEL            = os.environ.get('GROQ_MODEL',         'openai/gpt-oss-20b')
GROQ_VISION_MODEL     = os.environ.get('GROQ_VISION_MODEL',  'meta-llama/llama-4-scout-17b-16e-instruct')
GROQ_FAST_MODEL       = os.environ.get('GROQ_FAST_MODEL',    'openai/gpt-oss-20b')
GROQ_WHISPER_MODEL    = os.environ.get('GROQ_WHISPER_MODEL', 'whisper-large-v3')
GROQ_TIMEOUT          = int(os.environ.get('GROQ_TIMEOUT', '30'))
AI_MAX_TOKENS         = int(os.environ.get('AI_MAX_TOKENS', '1500'))
AI_FAST_MAX_TOKENS    = int(os.environ.get('AI_FAST_MAX_TOKENS', '768'))
AI_MAX_CONTEXT_CHARS  = int(os.environ.get('AI_MAX_CONTEXT_CHARS', '12000'))
AI_TEMPERATURE        = float(os.environ.get('AI_TEMPERATURE', '0.65'))
AI_STREAM_ENABLED     = os.environ.get('AI_STREAM_ENABLED', 'true').lower() == 'true'

# Marketplace
DELIVERY_FEE_NPR = int(os.environ.get('DELIVERY_FEE_NPR', '100'))

# City configuration
CITY_NAME = os.environ.get('CITY_NAME', 'Bhaktapur')
CITY_COUNTRY = os.environ.get('CITY_COUNTRY', 'Nepal')
CITY_LAT = float(os.environ.get('CITY_LAT', '27.6720'))
CITY_LNG = float(os.environ.get('CITY_LNG', '85.4298'))
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:8000')

# Khalti Payment Gateway
KHALTI_SECRET_KEY = os.environ.get('KHALTI_SECRET_KEY', '')  # Get from khalti.com merchant dashboard
KHALTI_PUBLIC_KEY = os.environ.get('KHALTI_PUBLIC_KEY', '')
KHALTI_API_URL = 'https://a.khalti.com/api/v2/'  # sandbox: https://a.khalti.com/api/v2/, prod: https://khalti.com/api/v2/

# ── Celery ────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_ALWAYS_EAGER = os.environ.get('CELERY_TASK_ALWAYS_EAGER', 'False') == 'True'

# django-celery-beat is optional in some environments (e.g. dev without extra dependency).
# If missing, fall back to Celery's default scheduler.
try:
    import django_celery_beat  # noqa: F401
except Exception:
    CELERY_BEAT_SCHEDULER = None

from celery.schedules import crontab  # noqa: E402
CELERY_BEAT_SCHEDULE = {

    # Vectorize new KB entries opportunistically — every 5 min
    'embed-pending-kb-5min': {
        'task':     'chatbot.tasks.embed_pending_kb_entries',
        'schedule': 300.0,
    },
    # Batch-vectorize admin-added KB entries — every 10 min
    'embed-new-kb-batch-10min': {
        'task':     'chatbot.tasks.embed_new_kb_entries_batch',
        'schedule': 600.0,
    },
    # Pull municipality news into KB — every 6 hours
    'sync-announcements-6h': {
        'task':     'chatbot.tasks.sync_municipal_announcements',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    # Warm the context cache so first request after expiry is instant — every 8 min
    'warm-context-cache-8min': {
        'task':     'chatbot.tasks.warm_context_cache',
        'schedule': 480.0,
    },
    # Prune stale auto-generated KB entries — daily at 2 AM
    'prune-stale-auto-kb-daily': {
        'task':     'chatbot.tasks.prune_stale_auto_kb',
        'schedule': crontab(minute=0, hour=2),
    },
    # Warm the homepage cache so first visitor never sees a cold-start lag — every 10 min
    'warm-homepage-cache-10min': {
        'task':     'core.tasks.warm_homepage_cache',
        'schedule': 600.0,
    },
}

# ── TOTP / 2FA encryption ──────────────────────────────────────────────────
# Fernet key used to encrypt otp_secret at rest. Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOTP_ENCRYPTION_KEY = os.environ.get('TOTP_ENCRYPTION_KEY', '')

# ── File upload safety ─────────────────────────────────────────────────────
# File upload safety
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']

# ── Social Auth (OAuth) ────────────────────────────────────────────────────
# Keep Django password auth unambiguous.
# Social Auth will still work via its own auth URLs/callbacks.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'social_core.backends.google.GoogleOAuth2',
    'social_core.backends.github.GithubOAuth2',
]

# Social Auth provider/backends configuration
# Ensure social-core can resolve backend names used in URL patterns.
# NOTE: social-django routes use provider keys as backend names (google-oauth2 / github).
SOCIAL_AUTH_PROVIDERS = {

    'google-oauth2': {
        'SCOPE': ['email', 'profile'],
        'AUTH_EXTRA_ARGUMENTS': {'access_type': 'online', 'prompt': 'select_account'},
    },
    
}

# social_core expects backend names (e.g. 'google-oauth2', 'github') to be registered.
# social-core (version in this environment) reads SOCIAL_AUTH_AUTHENTICATION_BACKENDS
# to load social backends. The values are backend *names* used in the URL patterns.
SOCIAL_AUTH_AUTHENTICATION_BACKENDS = [
    'social_core.backends.google.GoogleOAuth2',
    'social_core.backends.github.GithubOAuth2',
]

# Ensure the social-auth session key works with Django sessions.
SOCIAL_AUTH_USE_SESSION = True






INSTALLED_APPS += [
    'social_django',
    'complaints',
    'dashboard.apps.DashboardConfig',
]

# django-celery-beat is optional; only add it if installed.
try:
    import django_celery_beat  # noqa: F401
    INSTALLED_APPS.append('django_celery_beat')
except Exception:
    pass


MIDDLEWARE += ['social_django.middleware.SocialAuthExceptionMiddleware']

TEMPLATES[0]['OPTIONS']['context_processors'] += [
    'social_django.context_processors.backends',
    'social_django.context_processors.login_redirect',
]

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY    = os.environ.get('GOOGLE_OAUTH2_KEY', '')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.environ.get('GOOGLE_OAUTH2_SECRET', '')
SOCIAL_AUTH_GITHUB_KEY           = os.environ.get('GITHUB_KEY', '')
SOCIAL_AUTH_GITHUB_SECRET        = os.environ.get('GITHUB_SECRET', '')
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE  = ['email', 'profile']
SOCIAL_AUTH_GITHUB_SCOPE         = ['user:email']

SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'accounts.pipeline.create_or_update_user_from_google',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
    'accounts.pipeline.set_default_role',
)






# social-auth is strict about redirect hosts; allow your deployment hosts.
# In dev (DEBUG=True) this lets localhost/http redirects work.
# In production/behind proxy, allow the host from SITE_URL plus common public tunnel domains.
if DEBUG:
    SOCIAL_AUTH_ALLOWED_REDIRECT_HOSTS = ['localhost', '127.0.0.1']
else:
    _site_url = os.environ.get('SITE_URL', '')
    _host = ''
    try:
        from urllib.parse import urlparse
        _host = urlparse(_site_url).netloc
    except Exception:
        _host = ''

    SOCIAL_AUTH_ALLOWED_REDIRECT_HOSTS = [
        h for h in (
            _host,
            'localhost',
            '127.0.0.1',
            # ngrok-free tunnels (adjust if you use a different ngrok plan)
            '*.ngrok-free.app',
            '*.ngrok-free.dev',
        ) if h
    ]

# Make sure the OAuth callback uses the expected scheme.
# When behind a proxy that terminates TLS externally, Google sees https://<host>/... even if
# your internal Django server is http://. Using BEHIND_PROXY keeps social-auth consistent.
SOCIAL_AUTH_REDIRECT_IS_HTTPS = bool(BEHIND_PROXY) or bool(SECURE_SSL_REDIRECT)

SOCIAL_AUTH_LOGIN_ERROR_URL        = '/auth/error/google-oauth2/'
# Do NOT raise on OAuth failures in production; we route to a friendly error page.
SOCIAL_AUTH_RAISE_EXCEPTIONS       = False



# Make sure social-auth uses your custom user model.
SOCIAL_AUTH_USER_MODEL = 'accounts.User'

# Ensure social-auth uses the same session framework as Django.
# (Fixes failures where the strategy can’t access request.session.)
SOCIAL_AUTH_STRATEGY = 'social_django.strategy.DjangoStrategy'
SOCIAL_AUTH_SESSION_TYPE = 'django.contrib.sessions.backends.db'

# Storage backend for association state.
SOCIAL_AUTH_ASSOCIATE_BY_MAIL = False
SOCIAL_AUTH_USE_SESSION = True

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY    = False  # must be False for JS AJAX CSRF reads

# Needed when using an HTTPS public URL (ngrok) with Google OAuth.
# OAuth involves cross-site redirects/callbacks; Django must trust the external
# Origin header (especially when DEBUG=False behind a proxy).
_CSRF = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _CSRF.split(',') if o.strip()]

CSRF_TRUSTED_ORIGINS += [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://localhost:8000',
    'https://127.0.0.1:8000',
]

# ngrok tunnels are only trusted in development — never in production.
if DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        'https://*.ngrok-free.app',
        'https://*.ngrok-free.dev',
        'http://*.ngrok-free.app',
        'http://*.ngrok-free.dev',
    ]

CSRF_TRUSTED_ORIGINS = sorted(set(CSRF_TRUSTED_ORIGINS))


# Static version — bump on each deploy to force SW re-cache
STATIC_VERSION = os.environ.get('STATIC_VERSION', '1')

# ── Logging ────────────────────────────────────────────────────────────────────
import logging.config as _lc

_LOG_DIR = BASE_DIR / 'logs'
_LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_errors': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(_LOG_DIR / 'errors.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'ERROR',
        },
        'file_audit': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(_LOG_DIR / 'audit.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 20,
            'formatter': 'verbose',
            'level': 'INFO',
        },
        'file_info': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(_LOG_DIR / 'app.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 3,
            'formatter': 'verbose',
            'level': 'INFO',
        },
    },
    'root': {
        'handlers': ['console', 'file_errors'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_errors'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file_errors'],
            'level': 'ERROR',
            'propagate': False,
        },
        # App-level loggers — WARNING in production, INFO in dev
        'accounts': {'handlers': ['console', 'file_info', 'file_errors'], 'level': 'INFO' if DEBUG else 'WARNING', 'propagate': False},
        'complaints': {'handlers': ['console', 'file_info', 'file_errors'], 'level': 'INFO' if DEBUG else 'WARNING', 'propagate': False},
        'marketplace': {'handlers': ['console', 'file_info', 'file_errors'], 'level': 'INFO' if DEBUG else 'WARNING', 'propagate': False},
        'civic': {'handlers': ['console', 'file_info', 'file_errors'], 'level': 'INFO' if DEBUG else 'WARNING', 'propagate': False},
        'chatbot': {'handlers': ['console', 'file_info', 'file_errors'], 'level': 'INFO' if DEBUG else 'WARNING', 'propagate': False},
        'core': {'handlers': ['console', 'file_info', 'file_errors'], 'level': 'INFO' if DEBUG else 'WARNING', 'propagate': False},
        # Audit trail stays at INFO in production — WARNING would silently
        # discard exactly the record §35 requires.
        'municipal_ai.audit': {'handlers': ['file_audit'], 'level': 'INFO', 'propagate': False},
        'municipal_ai.tools': {'handlers': ['console', 'file_errors'], 'level': 'ERROR', 'propagate': False},
    },
}

# ── Sentry error tracking (set SENTRY_DSN in .env to enable) ──────────────────
_sentry_dsn = os.environ.get('SENTRY_DSN', '')
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[DjangoIntegration()],
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
    except ImportError:
        pass  # sentry-sdk not installed — add it to requirements.txt

# ── Rate limiting defaults (overridable via env) ───────────────────────────────
RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', '60'))
RATE_LIMIT_REQUESTS = int(os.environ.get('RATE_LIMIT_REQUESTS', '60'))
