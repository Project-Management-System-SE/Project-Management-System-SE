from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure


def csrf_failure(request, reason=""):
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse(
            {
                "success": False,
                "error": "Your security token is invalid or expired. Refresh the page and try again.",
            },
            status=403,
        )
    return django_csrf_failure(request, reason=reason)
