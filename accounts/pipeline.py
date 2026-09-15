import logging
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

User = get_user_model()


def _safe_preview(x, max_len: int = 400) -> str:
    try:
        s = json.dumps(x, default=str, ensure_ascii=False) if not isinstance(x, str) else x
        s = s if len(s) <= max_len else s[:max_len] + '…'
        return s
    except Exception:
        try:
            return str(x)[:max_len]
        except Exception:
            return '<unprintable>'


def _log_step(step_name: str, *, strategy=None, backend=None, uid=None, details=None, response=None, user=None, extra=None):
    # Avoid blowing up OAuth completion due to logging failures.
    try:
        logger.info(
            'social-auth step %s',
            step_name,
            extra={
                'backend': getattr(backend, 'name', getattr(backend, '__class__', type(backend)).__name__),
                'uid': uid,
                'details': _safe_preview(details) if details is not None else None,
                'response': _safe_preview(response) if response is not None else None,
                'user_pk': getattr(user, 'pk', None),
                'user_email': getattr(user, 'email', None),
                'extra': _safe_preview(extra) if extra is not None else None,
            },
        )
    except Exception:
        return


def _wrap_pipeline_step(step_name: str, func):
    """Logging wrapper around a social-core pipeline step.

    IMPORTANT: This wrapper must be signature-safe.
    """

    def _wrapped(*args, **kwargs):
        # Best-effort extraction only for logging (must not mutate kwargs).
        strategy = kwargs.get('strategy') or (args[0] if len(args) > 0 else None)
        backend = kwargs.get('backend') or (args[2] if len(args) > 2 else None)
        uid = kwargs.get('uid') or (args[3] if len(args) > 3 else None)
        details = kwargs.get('details') or (args[1] if len(args) > 1 else None)
        response = kwargs.get('response') or (args[4] if len(args) > 4 else None)
        user = kwargs.get('user')

        _log_step(
            step_name + ' ENTER',
            strategy=strategy,
            backend=backend,
            uid=uid,
            details=details,
            response=response,
            user=user,
        )

        result = func(*args, **kwargs)

        # Best-effort extraction for logging.
        _user = None
        _extra = {}
        try:
            _extra['returned_type'] = str(type(result))
            if isinstance(result, dict):
                _extra['returned_keys'] = sorted(list(result.keys()))
                if 'user' in result and result['user'] is not None:
                    _user = result['user']
                    _extra['returned_user_pk'] = getattr(_user, 'pk', None)
                    _extra['returned_user_email'] = getattr(_user, 'email', None)
            else:
                if hasattr(result, 'pk'):
                    _user = result
                    _extra['returned_user_pk'] = getattr(_user, 'pk', None)
                    _extra['returned_user_email'] = getattr(_user, 'email', None)
        except Exception:
            pass

        _log_step(
            step_name + ' EXIT',
            strategy=strategy,
            backend=backend,
            uid=uid,
            details=details,
            response=response,
            user=_user,
            extra=_extra,
        )
        return result

    _wrapped.__name__ = func.__name__
    _wrapped.__doc__ = func.__doc__
    return _wrapped





def _get_email_from_details(details: dict) -> str | None:
    if not isinstance(details, dict):
        return None
    email = details.get('email')
    if not email:
        return None
    return str(email).strip().lower() or None


def google_auth_log_event(event_name: str, **extra):
    # Central place for consistent auth logging.
    logger.info("%s %s", event_name, extra)


def _ensure_profile(user):
    """Create/update Profile for a given User.

    This must never crash the OAuth flow.
    """
    try:
        # Import lazily to avoid circular imports.
        from accounts.models import Profile

        profile, _created = Profile.objects.get_or_create(user=user)
        return profile
    except Exception:
        logger.exception('Failed to ensure Profile')
        return None


def create_or_update_user_from_google(strategy, details, backend, uid, response, *args, **kwargs):

    """Create or update a User from Google OAuth details.

    This pipeline must never crash OAuth completion.
    If it fails, we:
      1) log the full exception
      2) persist the exact failure message into the session
      3) re-raise so SocialAuthExceptionMiddleware redirects to the error page.
    """
    # Best-effort: store the last error message in session so error page shows it.
    # social-auth gives us `strategy`, which for DjangoStrategy can access request/session.
    def _set_session_error(msg: str):
        try:
            request = getattr(strategy, 'request', None)
            if request is not None:
                request.session['social_auth_error_message'] = msg
        except Exception:
            return

    try:
        email = _get_email_from_details(details)
        if not email:
            google_auth_log_event('OAuth failure: missing email', backend=getattr(backend, 'name', None))
            _set_session_error('Google OAuth did not return an email address.')
            raise ValueError('Google OAuth did not return an email address.')

        # Google provides names in various formats.
        first_name = (details.get('first_name') or '').strip()
        last_name = (details.get('last_name') or '').strip()
        if not first_name and details.get('name'):
            parts = str(details.get('name')).split(' ', 1)
            first_name = parts[0].strip()
            last_name = parts[1].strip() if len(parts) > 1 else ''

        # Avatar URL (may be absent)
        avatar_url = None
        if isinstance(details.get('picture'), str):
            avatar_url = details.get('picture').strip() or None

        # Google identity
        # Strategy auth response usually has 'sub' for OIDC-style providers, but
        # social-auth also has backend-assigned uid.
        google_id = None
        try:
            google_id = response.get('sub') or uid
        except Exception:
            google_id = uid

        # Create/update user atomically.
        logger.info('Google login started', extra={'email': email, 'google_id': google_id})

        with transaction.atomic():
            try:
                user = User.objects.select_for_update().get(email=email)
                created = False
            except User.DoesNotExist:
                created = True
                # Need a stable username. Use email local-part; ensure uniqueness.
                username_base = email.split('@', 1)[0]
                username = username_base
                i = 1
                while User.objects.filter(username=username).exists():
                    i += 1
                    username = f"{username_base}_{i}"

                # Populate required fields for custom user.
                user = User(
                    email=email,
                    username=username,
                    first_name=first_name or username_base,
                    last_name=last_name,
                    role='citizen',
                    provider=getattr(backend, 'name', None) or 'google-oauth2',
                    is_active=True,
                    is_email_verified=True,  # treat Google-verified email as verified
                )

                # Disable password login for social-only accounts (best-effort).
                try:
                    if hasattr(user, 'set_unusable_password'):
                        user.set_unusable_password()
                except Exception:
                    logger.exception('Failed to set unusable password')

                user.save()

            # Apply updates on every login.
            updated_fields = []
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updated_fields.append('first_name')
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                updated_fields.append('last_name')

            if not user.is_email_verified:
                user.is_email_verified = True
                updated_fields.append('is_email_verified')

            user.last_login = timezone.now()
            updated_fields.append('last_login')

            # Enforce role default.
            if not user.role:
                user.role = 'citizen'
                updated_fields.append('role')

            if updated_fields:
                user.save(update_fields=updated_fields)

            profile = _ensure_profile(user)

            # Store google identity + avatar (best-effort).
            if profile is not None:
                try:
                    if google_id and getattr(profile, 'google_id', None) != google_id:
                        profile.google_id = google_id
                        profile.save(update_fields=['google_id'])
                except Exception:
                    logger.exception('Failed to update Profile.google_id')

                if avatar_url:
                    # The URL comes from the provider's response, so it is
                    # fetched through the guarded client: https only, no
                    # redirects, public addresses only, size-capped, and the
                    # bytes decoded to confirm they are really an image.
                    try:
                        import uuid as _uuid

                        from core.safe_fetch import fetch_image

                        fetched = fetch_image(avatar_url)
                        if fetched is not None:
                            data, ext = fetched
                            filename = f"google_avatar_{_uuid.uuid4().hex}.{ext}"
                            profile.avatar.save(filename, ContentFile(data), save=True)
                    except Exception:
                        logger.exception('Failed to download/save Google avatar')

        if created:
            google_auth_log_event(
                'User created from Google',
                email=email,
                google_id=google_id,
                user_pk=getattr(user, "pk", None),
            )
        else:
            google_auth_log_event(
                'Existing user logged in via Google',
                email=email,
                google_id=google_id,
                user_pk=getattr(user, "pk", None),
            )

        # Extra confirmation for debugging associate_user failures
        logger.info(
            "OAuth pipeline returning user for association",
            extra={"email": email, "google_id": google_id, "user_pk": getattr(user, "pk", None)},
        )
        return {"user": user}


    except Exception as e:
        # Capture exact exception message for debugging + show on error page.
        try:
            msg = f"{type(e).__name__}: {e}"
        except Exception:
            msg = 'Google OAuth processing failed (unknown error).'
        google_auth_log_event('OAuth failure: exception in pipeline', error=msg)
        _set_session_error(msg)
        logger.exception('OAuth pipeline failed: %s', msg)
        raise

    # (unreachable)




def set_default_role(backend, user, response, *args, **kwargs):
    """Keep role sane after pipeline runs."""
    if user and not getattr(user, 'role', None):
        user.role = 'citizen'
        user.save(update_fields=['role'])


# ---------------------------------------------------------------------------
# Social-auth debug pipeline wrappers (log entry/exit around each step)
# ---------------------------------------------------------------------------


def debug_social_details(*args, **kwargs):
    from social_core.pipeline.social_auth import social_details
    # Accept any signature social-core provides.
    return _wrap_pipeline_step('social_details', social_details)(*args, **kwargs)



def debug_social_uid(*args, **kwargs):
    from social_core.pipeline.social_auth import social_uid
    return _wrap_pipeline_step('social_uid', social_uid)(*args, **kwargs)



def debug_auth_allowed(*args, **kwargs):
    from social_core.pipeline.social_auth import auth_allowed
    return _wrap_pipeline_step('auth_allowed', auth_allowed)(*args, **kwargs)



def debug_social_user(*args, **kwargs):
    from social_core.pipeline.social_auth import social_user
    return _wrap_pipeline_step('social_user', social_user)(*args, **kwargs)



def debug_get_username(*args, **kwargs):
    from social_core.pipeline.user import get_username
    return _wrap_pipeline_step('get_username', get_username)(*args, **kwargs)



# NOTE: Intentionally keep no debug_associate_user.











def debug_load_extra_data(*args, **kwargs):
    from social_core.pipeline.social_auth import load_extra_data
    return load_extra_data(*args, **kwargs)




def debug_user_details(*args, **kwargs):
    from social_core.pipeline.user import user_details
    return _wrap_pipeline_step('user_details', user_details)(*args, **kwargs)



