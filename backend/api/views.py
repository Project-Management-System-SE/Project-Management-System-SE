import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from projects.models import Project, Sprint, Milestone
from projects.permissions import visible_projects_for, can_manage_project
from projects.workflow import is_valid_transition
from tasks.models import Task
from tasks.permissions import (
    can_view_tasks_for,
    can_create_task_in,
    can_edit_task,
    can_delete_task,
    can_reassign_task,
)
from .auth import api_auth_required
from .helpers import (
    error_response,
    serialize_project,
    serialize_task,
    success_response,
)


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def project_list_api(request):
    projects = visible_projects_for(request.user).select_related("owner")
    data = [serialize_project(p) for p in projects]
    return success_response({"projects": data, "count": len(data)})


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def project_detail_api(request, project_id):
    try:
        project = visible_projects_for(request.user).select_related("owner").get(pk=project_id)
    except Project.DoesNotExist:
        return error_response("Project not found or access denied.", status=404)

    return success_response(serialize_project(project))


@csrf_exempt
@api_auth_required
@require_http_methods(["GET", "POST"])
def task_list_create_api(request, project_id):
    try:
        project = visible_projects_for(request.user).get(pk=project_id)
    except Project.DoesNotExist:
        return error_response("Project not found or access denied.", status=404)

    if request.method == "GET":
        tasks_qs = project.tasks.select_related("assignee", "sprint", "milestone")
        status_filter = request.GET.get("status")
        if status_filter:
            tasks_qs = tasks_qs.filter(status=status_filter)
        priority_filter = request.GET.get("priority")
        if priority_filter:
            tasks_qs = tasks_qs.filter(priority=priority_filter)
        assignee_id = request.GET.get("assignee_id")
        if assignee_id:
            tasks_qs = tasks_qs.filter(assignee_id=assignee_id)

        data = [serialize_task(t) for t in tasks_qs]
        return success_response({"tasks": data, "count": len(data)})

    if not can_create_task_in(request.user, project):
        return error_response("You do not have permission to create tasks in this project.", status=403)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return error_response("Invalid JSON payload.", status=400)

    title = (body.get("title") or "").strip()
    if len(title) < 3:
        return error_response("Task title must be at least 3 characters long.", status=400)

    priority = body.get("priority", Task.Priority.MEDIUM)
    if priority not in Task.Priority.values:
        return error_response(f"Invalid priority '{priority}'.", status=400)

    assignee = None
    assignee_id = body.get("assignee_id")
    if assignee_id:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            assignee = User.objects.get(pk=assignee_id)
            is_valid_assignee = (
                project.owner_id == assignee.pk
                or project.memberships.filter(user=assignee).exists()
            )
            if not is_valid_assignee:
                return error_response("Selected assignee is not an active member of this project.", status=400)
        except User.DoesNotExist:
            return error_response("Assignee user does not exist.", status=400)

    due_date = body.get("due_date")
    if due_date:
        import datetime
        try:
            due_date = datetime.date.fromisoformat(due_date)
            if project.start_date and due_date < project.start_date:
                return error_response("Due date cannot precede project start date.", status=400)
        except ValueError:
            return error_response("Invalid due_date format (YYYY-MM-DD expected).", status=400)

    task = Task.objects.create(
        project=project,
        title=title,
        description=body.get("description", ""),
        priority=priority,
        status=Task.Status.TODO,
        assignee=assignee,
        due_date=due_date,
        created_by=request.user,
    )
    return success_response(serialize_task(task), status=201, message="Task created successfully.")


@csrf_exempt
@api_auth_required
@require_http_methods(["GET", "PATCH", "DELETE"])
def task_detail_api(request, task_id):
    try:
        task = Task.objects.select_related("project", "assignee").get(pk=task_id)
    except Task.DoesNotExist:
        return error_response("Task not found.", status=404)

    if not can_view_tasks_for(request.user, task.project):
        return error_response("Task not found or access denied.", status=404)

    if request.method == "GET":
        return success_response(serialize_task(task))

    if request.method == "DELETE":
        if not can_delete_task(request.user, task):
            return error_response("You do not have permission to delete this task.", status=403)
        task_id = task.pk
        task.delete()
        return success_response({"deleted_task_id": task_id}, message="Task deleted successfully.")

    if not can_edit_task(request.user, task):
        return error_response("You do not have permission to edit this task.", status=403)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return error_response("Invalid JSON payload.", status=400)

    if "title" in body:
        title = body["title"].strip()
        if len(title) < 3:
            return error_response("Task title must be at least 3 characters long.", status=400)
        task.title = title

    if "description" in body:
        task.description = body["description"]

    if "priority" in body:
        priority = body["priority"]
        if priority not in Task.Priority.values:
            return error_response(f"Invalid priority '{priority}'.", status=400)
        task.priority = priority

    if "assignee_id" in body:
        new_assignee_id = body["assignee_id"]
        if new_assignee_id != task.assignee_id and not can_reassign_task(request.user, task):
            return error_response("You do not have permission to reassign this task.", status=403)
        if new_assignee_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                new_assignee = User.objects.get(pk=new_assignee_id)
                task.assignee = new_assignee
            except User.DoesNotExist:
                return error_response("Assignee user does not exist.", status=400)
        else:
            task.assignee = None

    task.save()
    return success_response(serialize_task(task), message="Task updated successfully.")


@csrf_exempt
@api_auth_required
@require_http_methods(["POST"])
def task_status_api(request, task_id):
    try:
        task = Task.objects.select_related("project").get(pk=task_id)
    except Task.DoesNotExist:
        return error_response("Task not found.", status=404)

    if not can_view_tasks_for(request.user, task.project):
        return error_response("Task not found or access denied.", status=404)

    if not can_edit_task(request.user, task):
        return error_response("You do not have permission to update status for this task.", status=403)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return error_response("Invalid JSON payload.", status=400)

    new_status = body.get("status")
    if not new_status or new_status not in Task.Status.values:
        return error_response(f"Invalid status '{new_status}'. Allowed: {list(Task.Status.values)}", status=400)

    if not is_valid_transition(task.project, task.status, new_status):
        return error_response(
            f"Transition from '{task.status}' to '{new_status}' is not permitted by project workflow rules.",
            status=400,
        )

    task.status = new_status
    task.save()
    return success_response(serialize_task(task), message="Task status updated successfully.")
