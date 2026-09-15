"""Guarded outbound fetching.

The only user-influenced outbound request in this application is the social
avatar download, whose URL arrives in an OAuth provider's response. Fetching
it unguarded gives an attacker who can shape that response a request issued
from inside the network — cloud metadata endpoints and loopback services are
the usual targets.

Everything here is a restriction: https only, no redirects, public addresses
only, a hard byte ceiling read in chunks, and image content verified by
decoding rather than by trusting the declared type.
"""
import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger('municipal_ai.tools')

ALLOWED_SCHEMES = ('https',)
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 5


class UnsafeURL(Exception):
    """The URL is not one we are willing to fetch."""


def _resolved_addresses(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURL(f'unresolvable host: {exc}')
    return {info[4][0] for info in infos}


def assert_safe_url(url):
    """Raise UnsafeURL unless this is an https URL to a public address."""
    if not url or not isinstance(url, str):
        raise UnsafeURL('empty url')

    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURL(f'scheme not allowed: {parsed.scheme!r}')
    if not parsed.hostname:
        raise UnsafeURL('no hostname')

    for address in _resolved_addresses(parsed.hostname):
        ip = ipaddress.ip_address(address)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UnsafeURL(f'non-public address: {address}')
    return parsed


def fetch_image(url, max_bytes=MAX_BYTES):
    """Return (bytes, extension) for a verified image, or None.

    Residual risk: the host is resolved for the check and resolved again by
    the HTTP client, so a DNS rebind between the two could still reach a
    private address. Redirects are disabled, which removes the far more
    practical version of that attack.
    """
    import requests

    try:
        assert_safe_url(url)
    except UnsafeURL as exc:
        logger.warning('refused outbound fetch: %s', exc)
        return None

    try:
        with requests.get(url, timeout=TIMEOUT, stream=True,
                          allow_redirects=False) as resp:
            if resp.status_code != 200:
                return None
            if not resp.headers.get('content-type', '').startswith('image/'):
                return None

            declared = resp.headers.get('content-length')
            if declared and int(declared) > max_bytes:
                return None

            chunks, total = [], 0
            for chunk in resp.iter_content(8192):
                total += len(chunk)
                if total > max_bytes:
                    logger.warning('refused outbound fetch: over %d bytes', max_bytes)
                    return None
                chunks.append(chunk)
    except Exception:
        logger.exception('outbound fetch failed')
        return None

    data = b''.join(chunks)
    return _verify_image(data)


def _verify_image(data):
    """Confirm the bytes really are an image, and say which kind."""
    if not data:
        return None
    try:
        import io

        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            fmt = (image.format or '').lower()
            image.verify()
    except Exception:
        return None

    extension = {'jpeg': 'jpg', 'png': 'png', 'webp': 'webp'}.get(fmt)
    if extension is None:
        return None
    return data, extension
