import hashlib

from django.conf import settings
from django.core.cache import cache

from .helpers import error_response


def throttle_api_request(request, user=None):
    window = settings.API_RATE_LIMIT_WINDOW_SECONDS
    limit = (
        settings.API_RATE_LIMIT_WRITE
        if request.method not in {"GET", "HEAD", "OPTIONS"}
        else settings.API_RATE_LIMIT_READ
    )
    if user is not None and getattr(user, "is_authenticated", False):
        identity = f"user:{user.pk}"
    else:
        identity = f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    key = f"api-throttle:{request.method}:{digest}"

    if cache.add(key, 1, timeout=window):
        request_count = 1
    else:
        try:
            request_count = cache.incr(key)
        except ValueError:
            if cache.add(key, 1, timeout=window):
                request_count = 1
            else:
                request_count = cache.incr(key)

    if request_count <= limit:
        return None

    response = error_response(
        "API rate limit exceeded. Try again later.",
        status=429,
        errors={"rate_limit": ["Request limit exceeded."]},
    )
    response["Retry-After"] = str(window)
    return response
