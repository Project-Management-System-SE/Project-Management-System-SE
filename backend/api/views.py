import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from projects.models import Project, ProjectMembership, Sprint, Milestone
from projects.permissions import visible_projects_for, can_manage_project
from tasks.models import Task
from tasks.permissions import (
    can_view_tasks_for,
    can_create_task_in,
    can_edit_task,
    can_delete_task,
    can_reassign_task,
)
from tasks.workflow import (
    is_valid_workflow_transition,
    set_task_workflow_status,
    workflow_choices_for,
    workflow_status_key,
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
    valid_statuses = [value for value, _ in workflow_choices_for(task.project)]
    if not new_status or new_status not in valid_statuses:
        return error_response(
            f"Invalid status '{new_status}'. Allowed: {valid_statuses}",
            status=400,
        )

    current_status = workflow_status_key(task)
    if not is_valid_workflow_transition(
        current_status,
        new_status,
        task.project,
        user=request.user,
    ):
        return error_response(
            f"Transition from '{current_status}' to '{new_status}' is not permitted by project workflow rules.",
            status=400,
        )

    try:
        set_task_workflow_status(task, new_status, task.project)
        task.save()
    except ValidationError as exc:
        message = "; ".join(exc.messages)
        return error_response(message, status=400)
    return success_response(serialize_task(task), message="Task status updated successfully.")


def _serialize_membership(membership):
    return {
        "id": membership.pk,
        "project_id": membership.project_id,
        "user": {
            "id": membership.user_id,
            "name": membership.user.full_name or membership.user.username,
            "email": membership.user.email,
        },
        "role": membership.project_role,
        "joined_at": membership.joined_at.isoformat(),
    }


def _read_api_json(request):
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, error_response("Invalid JSON payload.", status=400)
    if not isinstance(body, dict):
        return None, error_response("Request body must be a JSON object.", status=400)
    return body, None


@api_auth_required
@require_http_methods(["GET", "POST"])
def project_membership_api(request, project_id):
    project = visible_projects_for(request.user).filter(pk=project_id).first()
    if project is None:
        return error_response("Project not found or access denied.", status=404)

    if request.method == "GET":
        memberships = project.memberships.select_related("user").order_by("user_id")
        data = [_serialize_membership(membership) for membership in memberships]
        return success_response({"members": data, "count": len(data)})

    if not can_manage_project(request.user, project):
        return error_response("You do not have permission to manage project memberships.", status=403)

    body, error = _read_api_json(request)
    if error:
        return error
    user_id = body.get("user_id")
    role = body.get("role")
    if not user_id:
        return error_response("user_id is required.", status=400)
    if role not in ProjectMembership.Role.values:
        return error_response(
            f"role must be one of: {list(ProjectMembership.Role.values)}.",
            status=400,
        )
    if (
        role == ProjectMembership.Role.PROJECT_MANAGER
        and not request.user.is_admin
        and project.owner_id != request.user.pk
    ):
        return error_response("Only project owners or admins can add Project Managers.", status=403)

    User = get_user_model()
    try:
        member = User.objects.get(pk=user_id)
    except (User.DoesNotExist, TypeError, ValueError):
        return error_response("User not found.", status=400)

    if project.memberships.filter(user=member).exists():
        return error_response("This user is already a project member.", status=400)
    try:
        membership = ProjectMembership.objects.create(
            project=project,
            user=member,
            project_role=role,
        )
    except IntegrityError:
        return error_response("This user is already a project member.", status=400)
    return success_response(
        _serialize_membership(membership),
        status=201,
        message="Project member added successfully.",
    )


@api_auth_required
@require_http_methods(["PATCH", "DELETE"])
def project_membership_detail_api(request, project_id, membership_id):
    project = visible_projects_for(request.user).filter(pk=project_id).first()
    if project is None:
        return error_response("Project not found or access denied.", status=404)
    membership = project.memberships.select_related("user").filter(pk=membership_id).first()
    if membership is None:
        return error_response("Project membership not found.", status=404)
    if not can_manage_project(request.user, project):
        return error_response("You do not have permission to manage project memberships.", status=403)

    if membership.user_id == project.owner_id:
        return error_response("The project owner's membership cannot be changed or removed.", status=400)

    if request.method == "DELETE":
        if (
            not request.user.is_admin
            and project.owner_id != request.user.pk
            and membership.project_role == ProjectMembership.Role.PROJECT_MANAGER
        ):
            return error_response("Only project admins can remove Project Managers.", status=403)
        membership.delete()
        return success_response(
            {"deleted_membership_id": membership_id},
            message="Project member removed successfully.",
        )

    body, error = _read_api_json(request)
    if error:
        return error
    role = body.get("role")
    if role not in ProjectMembership.Role.values:
        return error_response(
            f"role must be one of: {list(ProjectMembership.Role.values)}.",
            status=400,
        )
    if (
        role == ProjectMembership.Role.PROJECT_MANAGER
        and not request.user.is_admin
        and project.owner_id != request.user.pk
    ):
        return error_response("Only project owners or admins can assign Project Manager role.", status=403)
    membership.project_role = role
    membership.save(update_fields=["project_role"])
    return success_response(
        _serialize_membership(membership),
        message="Project member role updated successfully.",
    )


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def sprint_list_api(request, project_id):
    try:
        project = visible_projects_for(request.user).get(pk=project_id)
    except Project.DoesNotExist:
        return error_response("Project not found or access denied.", status=404)

    sprints = project.sprints.all().order_by("start_date", "pk")
    data = [
        {
            "id": s.pk,
            "name": s.name,
            "status": s.status,
            "goal": s.goal,
            "start_date": s.start_date.isoformat() if s.start_date else None,
            "end_date": s.end_date.isoformat() if s.end_date else None,
            "task_count": s.tasks.count(),
        }
        for s in sprints
    ]
    return success_response({"sprints": data, "count": len(data)})


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def milestone_list_api(request, project_id):
    try:
        project = visible_projects_for(request.user).get(pk=project_id)
    except Project.DoesNotExist:
        return error_response("Project not found or access denied.", status=404)

    milestones = project.milestones.all().order_by("due_date", "pk")
    data = [
        {
            "id": m.pk,
            "name": m.name,
            "description": m.description,
            "due_date": m.due_date.isoformat() if m.due_date else None,
            "task_count": m.tasks.count(),
        }
        for m in milestones
    ]
    return success_response({"milestones": data, "count": len(data)})
