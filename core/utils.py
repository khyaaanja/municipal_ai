import base64
import hashlib
import io
import json
import struct
from django.core.cache import cache

MAX_AI_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AI_AUDIO_BYTES = 10 * 1024 * 1024


def parse_structured_json(value, default=None):
    """Parse a provider JSON object without guessing at missing or malformed data."""
    if default is None:
        default = {}
    if not isinstance(value, str):
        return default.copy() if isinstance(default, dict) else default
    text = value.strip()
    if text.startswith('```'):
        parts = text.split('```')
        if len(parts) < 3:
            return default.copy() if isinstance(default, dict) else default
        text = parts[1].strip()
        if text.lower().startswith('json'):
            text = text[4:].lstrip()
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return default.copy() if isinstance(default, dict) else default
    return parsed if isinstance(parsed, dict) else (default.copy() if isinstance(default, dict) else default)


def decode_image_base64(image_data: str, max_bytes: int = MAX_AI_IMAGE_BYTES):
    """Return decoded image bytes, or None for malformed/oversized/non-image input."""
    if not isinstance(image_data, str):
        return None
    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]
    try:
        raw = base64.b64decode(image_data, validate=True)
    except (ValueError, TypeError):
        return None
    if not raw or len(raw) > max_bytes:
        return None
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
    except Exception:
        return None
    return raw


def valid_uploaded_file(uploaded_file, max_bytes: int, content_prefix: str = '') -> bool:
    """Apply the same size/type boundary checks to uploaded media."""
    if not uploaded_file or uploaded_file.size > max_bytes:
        return False
    content_type = getattr(uploaded_file, 'content_type', '') or ''
    return not content_prefix or content_type.startswith(content_prefix)


def valid_uploaded_image(uploaded_file, max_bytes: int) -> bool:
    """Validate an uploaded image by size, declared type, and decoded bytes."""
    if not valid_uploaded_file(uploaded_file, max_bytes, 'image/'):
        return False
    try:
        from PIL import Image
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image.verify()
        uploaded_file.seek(0)
        return True
    except Exception:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return False


def get_client_ip(request):
    """Extract real client IP. Only trusts X-Forwarded-For when BEHIND_PROXY=True,
    and takes the last (proxy-added) address, not the first (user-controlled)."""
    from django.conf import settings
    if getattr(settings, 'BEHIND_PROXY', False):
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if xff:
            return xff.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def increment_rate_counter(key: str, ttl: int) -> int:
    """Atomically increment a cache counter. Returns the new count."""
    cache.add(key, 0, ttl)
    return cache.incr(key)


def compress_image_base64(image_data: str, max_width: int = 640) -> str:
    """
    Compress a base64-encoded JPEG image by decoding, resizing proportional
    to max_width, re-encoding at 70% quality reducing Groq API token cost ~60%.
    If PIL is not available, returns original data unchanged.
    Returns base64 string without data-URL prefix.
    """
    try:
        from PIL import Image
    except ImportError:
        return image_data

    try:
        raw = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(raw))
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        w, h = img.size
        if w > max_width:
            ratio = max_width / float(w)
            new_h = int(h * ratio)
            img = img.resize((max_width, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=70, optimize=True)
        return base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        return image_data


def get_image_token_estimate(image_data: str) -> int:
    """
    Rough estimate of token cost for a vision API image.
    Groq charges ~258 tokens per 256x256 tile.
    """
    try:
        raw_len = len(base64.b64decode(image_data))
        approx_pixels = raw_len * 4
        approx_tiles = max(1, approx_pixels // (256 * 256))
        return approx_tiles * 258
    except Exception:
        return 1000


def image_hash(image_data: str) -> str:
    """
    Compute a fast perceptual-ish hash for base64 image data.
    Used for caching identical scan results.
    """
    try:
        raw = base64.b64decode(image_data)
        head = raw[:4096]
        size_bytes = struct.pack('>I', len(raw))
        return hashlib.sha256(head + size_bytes).hexdigest()[:16]
    except Exception:
        return hashlib.sha256(image_data.encode()[:500]).hexdigest()[:16]
