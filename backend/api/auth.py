from django.http import JsonResponse
from functools import wraps


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
                request.user = api_token.user
                return view_func(request, *args, **kwargs)
            except APIToken.DoesNotExist:
                return JsonResponse(
                    {"status": "error", "message": "Invalid or expired API token."},
                    status=401,
                )

        if request.user.is_authenticated and request.method in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            return view_func(request, *args, **kwargs)

        if request.user.is_authenticated:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "An API token is required for unsafe requests.",
                },
                status=403,
            )

        return JsonResponse(
            {"status": "error", "message": "Authentication required. Provide a valid Bearer token or session."},
            status=401,
        )

    return _wrapped
