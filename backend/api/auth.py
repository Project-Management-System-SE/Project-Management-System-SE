from django.http import JsonResponse
from functools import wraps

from .throttling import throttle_api_request


def api_auth_required(view_func):
    """Decorator that supports session authentication and API Token header authentication."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") or auth_header.startswith("Token "):
            token_str = auth_header.split(" ", 1)[1].strip()
            from .models import APIToken
            try:
                api_token = APIToken.objects.select_related("user").get(
                    key=token_str, is_active=True
                )
            except APIToken.DoesNotExist:
                throttled_response = throttle_api_request(request)
                if throttled_response:
                    return throttled_response
                return JsonResponse(
                    {"status": "error", "message": "Invalid or expired API token."},
                    status=401,
                )
            request.user = api_token.user
            throttled_response = throttle_api_request(request, user=api_token.user)
            if throttled_response:
                return throttled_response
            return view_func(request, *args, **kwargs)

        if request.user.is_authenticated and request.method in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            throttled_response = throttle_api_request(request, user=request.user)
            if throttled_response:
                return throttled_response
            return view_func(request, *args, **kwargs)

        if request.user.is_authenticated:
            throttled_response = throttle_api_request(request, user=request.user)
            if throttled_response:
                return throttled_response
            return JsonResponse(
                {
                    "status": "error",
                    "message": "An API token is required for unsafe requests.",
                },
                status=403,
            )

        throttled_response = throttle_api_request(request)
        if throttled_response:
            return throttled_response
        return JsonResponse(
            {"status": "error", "message": "Authentication required. Provide a valid Bearer token or session."},
            status=401,
        )

    return _wrapped
