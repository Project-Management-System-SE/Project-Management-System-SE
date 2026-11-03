import json
from decimal import Decimal
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
