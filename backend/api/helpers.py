import json
from datetime import date
from decimal import Decimal
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse


def success_response(data, status=200, message=None):
    payload = {"status": "success", "data": data}
    if message:
        payload["message"] = message
    return JsonResponse(payload, status=status)


def error_response(message, status=400, errors=None):
    payload = {"status": "error", "message": message}
    if errors:
        payload["errors"] = errors
    return JsonResponse(payload, status=status)


def paginate_queryset(request, queryset, *, default_page_size=25, max_page_size=100):
    page_values = request.GET.getlist("page")
    page_size_values = request.GET.getlist("page_size")
    if len(page_values) > 1 or len(page_size_values) > 1:
        return None, error_response(
            "page and page_size may each be specified only once.",
            status=400,
        )

    raw_page = page_values[0] if page_values else "1"
    raw_page_size = page_size_values[0] if page_size_values else str(default_page_size)
    try:
        page_number = int(raw_page)
        page_size = int(raw_page_size)
    except (TypeError, ValueError):
        return None, error_response("page and page_size must be integers.", status=400)
    if page_number < 1:
        return None, error_response("page must be a positive integer.", status=400)
    if not 1 <= page_size <= max_page_size:
        return None, error_response(
            f"page_size must be between 1 and {max_page_size}.",
            status=400,
        )

    paginator = Paginator(queryset, page_size)
    try:
        page = paginator.page(page_number)
    except (EmptyPage, PageNotAnInteger):
        return None, error_response("The requested page does not exist.", status=400)
    metadata = {
        "count": paginator.count,
        "page": page.number,
        "page_size": page_size,
        "next_page": page.next_page_number() if page.has_next() else None,
        "previous_page": page.previous_page_number() if page.has_previous() else None,
    }
    return (page, metadata), None


def validate_query_parameters(request, allowed):
    unknown = sorted(set(request.GET.keys()) - set(allowed))
    if unknown:
        return error_response(
            "Unknown query parameters.",
            status=400,
            errors={"query_parameters": unknown},
        )
    repeated = sorted(
        name for name in request.GET.keys() if len(request.GET.getlist(name)) > 1
    )
    if repeated:
        return error_response(
            "Query parameters may not be repeated.",
            status=400,
            errors={"query_parameters": repeated},
        )
    return None


def parse_query_date(request, parameter):
    value = request.GET.get(parameter)
    if not value:
        return None, None
    try:
        return date.fromisoformat(value), None
    except ValueError:
        return None, error_response(
            f"{parameter} must use YYYY-MM-DD format.",
            status=400,
            errors={parameter: ["Enter a valid date."]},
        )


def serialize_project(project):
    return {
        "id": project.pk,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "owner": {
            "id": project.owner_id,
            "name": project.owner.full_name or project.owner.username,
            "email": project.owner.email,
        },
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "due_date": project.due_date.isoformat() if project.due_date else None,
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


def serialize_task(task):
    return {
        "id": task.pk,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assignee": (
            {
                "id": task.assignee.pk,
                "name": task.assignee.full_name or task.assignee.username,
                "email": task.assignee.email,
            }
            if task.assignee
            else None
        ),
        "sprint_id": task.sprint_id,
        "milestone_id": task.milestone_id,
        "estimated_effort": str(task.estimated_effort or "0.00"),
        "actual_effort": str(task.actual_effort or "0.00"),
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }
