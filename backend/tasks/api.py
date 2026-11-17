import json
from functools import wraps

from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse

from projects.permissions import can_manage_project, visible_projects_for

from .audit import changes_from_form, record_audit
from .forms import TaskFilterForm, TaskForm
from .models import AuditLog, Task
from .notifications import notify_task_assignment, notify_task_status_change
from .permissions import can_create_task_in, can_edit_task
from .workflow import (
    initial_workflow_status,
    workflow_choices_for,
    workflow_status_key,
)


def _api_login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication is required."}, status=401)
        return view(request, *args, **kwargs)

    return wrapped


def _method_not_allowed(allowed_methods):
    response = JsonResponse(
        {"error": "Method not allowed."},
        status=405,
    )
    response["Allow"] = ", ".join(allowed_methods)
    return response


def _api_methods(*allowed_methods):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in allowed_methods:
                return _method_not_allowed(allowed_methods)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def _project_json(project):
    return {
        "id": project.pk,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "due_date": project.due_date.isoformat() if project.due_date else None,
        "owner": {
            "id": project.owner_id,
            "name": project.owner.full_name or project.owner.email,
        },
        "task_count": project.task_count,
        "completed_task_count": project.completed_task_count,
    }


def _task_json(task):
    return {
        "id": task.pk,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": workflow_status_key(task),
        "status_display": task.get_status_display(),
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "estimated_effort_hours": task.estimated_effort,
        "actual_effort_hours": task.actual_effort,
        "assignee": (
            {
                "id": task.assignee_id,
                "name": task.assignee.full_name or task.assignee.email,
                "email": task.assignee.email,
            }
            if task.assignee_id
            else None
        ),
        "sprint": (
            {"id": task.sprint_id, "name": task.sprint.name}
            if task.sprint_id
            else None
        ),
        "milestone": (
            {"id": task.milestone_id, "name": task.milestone.name}
            if task.milestone_id
            else None
        ),
        "labels": [label.name for label in task.labels.all()],
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _visible_project_or_404(user, project_id):
    return get_object_or_404(
        visible_projects_for(user).select_related("owner"),
        pk=project_id,
    )


def _project_tasks(project):
    return (
        project.tasks.select_related(
            "assignee",
            "created_by",
            "workflow_state",
            "sprint",
            "milestone",
        )
        .prefetch_related("labels")
        .order_by("-created_at", "-pk")
    )


def _read_json_object(request):
    if request.content_type != "application/json":
        return None, JsonResponse(
            {"error": "Content-Type must be application/json."},
            status=415,
        )
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, JsonResponse({"error": "Request body is not valid JSON."}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse(
            {"error": "Request body must be a JSON object."},
            status=400,
        )
    return payload, None


def _task_form_data(payload, project, task=None):
    allowed_fields = {
        "title",
        "description",
        "priority",
        "due_date",
        "estimated_effort",
        "actual_effort",
        "sprint",
        "milestone",
        "assignee",
        "status",
        "labels",
    }
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        return None, JsonResponse(
            {
                "error": "Unknown task fields.",
                "details": {"fields": unknown_fields},
            },
            status=400,
        )

    data = (
        {
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "due_date": task.due_date.isoformat() if task.due_date else "",
            "estimated_effort": (
                str(task.estimated_effort)
                if task.estimated_effort is not None
                else ""
            ),
            "actual_effort": (
                str(task.actual_effort)
                if task.actual_effort is not None
                else ""
            ),
            "sprint": task.sprint_id or "",
            "milestone": task.milestone_id or "",
            "assignee": task.assignee_id or "",
            "status": workflow_status_key(task),
            "labels": task.get_labels_as_string(),
        }
        if task
        else {
            "title": "",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "due_date": "",
            "estimated_effort": "",
            "actual_effort": "",
            "sprint": "",
            "milestone": "",
            "assignee": "",
            "status": initial_workflow_status(project),
            "labels": "",
        }
    )
    if "labels" in payload:
        labels = payload["labels"]
        if not isinstance(labels, list) or not all(
            isinstance(label, str) for label in labels
        ):
            return None, JsonResponse(
                {"error": "labels must be an array of strings."},
                status=400,
            )
        data["labels"] = ", ".join(labels)
    data.update({key: value for key, value in payload.items() if key != "labels"})
    return data, None


def _task_form_error(form):
    return JsonResponse(
        {
            "error": "Task validation failed.",
            "details": form.errors.get_json_data(),
        },
        status=400,
    )


def _form_validation_error(error):
    details = getattr(error, "message_dict", {"__all__": error.messages})
    return JsonResponse(
        {"error": "Task validation failed.", "details": details},
        status=400,
    )


@_api_login_required
@_api_methods("GET")
def api_project_list(request):
    projects = visible_projects_for(request.user).select_related("owner").annotate(
        task_count=Count("tasks", distinct=True),
        completed_task_count=Count(
            "tasks",
            filter=Q(tasks__status=Task.Status.DONE),
            distinct=True,
        ),
    )
    results = [_project_json(project) for project in projects]
    return JsonResponse({"count": len(results), "results": results})


@_api_login_required
@_api_methods("GET")
def api_project_detail(request, project_id):
    project = _visible_project_or_404(request.user, project_id)
    project.task_count = project.tasks.count()
    project.completed_task_count = project.tasks.filter(
        status=Task.Status.DONE
    ).count()
    return JsonResponse(_project_json(project))


@_api_login_required
@_api_methods("GET", "POST")
def api_project_task_list(request, project_id):
    project = _visible_project_or_404(request.user, project_id)
    if request.method == "POST":
        if not can_create_task_in(request.user, project):
            return JsonResponse({"error": "You cannot create tasks in this project."}, status=403)
        payload, error = _read_json_object(request)
        if error:
            return error
        data, error = _task_form_data(payload, project)
        if error:
            return error
        form = TaskForm(data=data, project=project)
        if not form.is_valid():
            return _task_form_error(form)
        try:
            with transaction.atomic():
                task = form.save(commit=False)
                task.project = project
                task.created_by = request.user
                task.save()
                form.save_m2m()
                record_audit(request.user, AuditLog.Action.CREATE, task)
                if task.assignee_id:
                    notify_task_assignment(task)
        except ValidationError as error:
            return _form_validation_error(error)
        response = JsonResponse(_task_json(task), status=201)
        response["Location"] = reverse(
            "api-project-task-detail",
            args=[project.pk, task.pk],
        )
        return response

    tasks = _project_tasks(project)
    filter_form = TaskFilterForm(request.GET, project=project)
    filter_form.fields["status"].choices = (
        ("", "All statuses"),
        *workflow_choices_for(project),
    )
    if not filter_form.is_valid():
        return JsonResponse(
            {
                "error": "Invalid task filters.",
                "details": filter_form.errors.get_json_data(),
            },
            status=400,
        )

    filters = filter_form.cleaned_data
    if filters["q"]:
        tasks = tasks.filter(
            Q(title__icontains=filters["q"])
            | Q(description__icontains=filters["q"])
        )
    if filters["assignee"]:
        tasks = tasks.filter(assignee=filters["assignee"])
    if filters["priority"]:
        tasks = tasks.filter(priority=filters["priority"])
    if filters["status"]:
        if project.workflow_states.exists():
            tasks = tasks.filter(workflow_state__key=filters["status"])
        else:
            tasks = tasks.filter(status=filters["status"])
    if filters["label"]:
        tasks = tasks.filter(labels=filters["label"])
    if filters["sprint"]:
        tasks = tasks.filter(sprint=filters["sprint"])

    try:
        page_number = int(request.GET.get("page", "1"))
        page_size = int(request.GET.get("page_size", "100"))
    except ValueError:
        return JsonResponse(
            {"error": "Page and page_size must be integers."},
            status=400,
        )
    if page_number < 1 or not 1 <= page_size <= 100:
        return JsonResponse(
            {"error": "Page must be positive and page_size must be between 1 and 100."},
            status=400,
        )

    paginator = Paginator(tasks, page_size)
    try:
        page = paginator.page(page_number)
    except (EmptyPage, PageNotAnInteger):
        return JsonResponse({"error": "The requested page does not exist."}, status=400)
    results = [_task_json(task) for task in page.object_list]
    return JsonResponse(
        {
            "project_id": project.pk,
            "count": paginator.count,
            "page": page.number,
            "page_size": page_size,
            "next_page": page.next_page_number() if page.has_next() else None,
            "previous_page": (
                page.previous_page_number() if page.has_previous() else None
            ),
            "results": results,
        }
    )


@_api_login_required
@_api_methods("GET", "PATCH", "DELETE")
def api_project_task_detail(request, project_id, task_id):
    project = _visible_project_or_404(request.user, project_id)
    task = get_object_or_404(_project_tasks(project), pk=task_id)
    if request.method == "GET":
        return JsonResponse(_task_json(task))
    if request.method == "DELETE":
        if not can_manage_project(request.user, project):
            return JsonResponse(
                {"error": "Only project managers can delete tasks."},
                status=403,
            )
        with transaction.atomic():
            record_audit(request.user, AuditLog.Action.DELETE, task)
            task.delete()
        return HttpResponse(status=204)

    if not can_edit_task(request.user, task):
        return JsonResponse({"error": "You cannot edit this task."}, status=403)
    payload, error = _read_json_object(request)
    if error:
        return error
    data, error = _task_form_data(payload, project, task=task)
    if error:
        return error
    previous_assignee_id = task.assignee_id
    previous_status = workflow_status_key(task)
    form = TaskForm(data=data, instance=task, project=project)
    if not form.is_valid():
        return _task_form_error(form)
    try:
        with transaction.atomic():
            changes = changes_from_form(form)
            task = form.save()
            if changes:
                record_audit(
                    request.user,
                    AuditLog.Action.UPDATE,
                    task,
                    changes=changes,
                )
            if task.assignee_id and task.assignee_id != previous_assignee_id:
                notify_task_assignment(task)
            if workflow_status_key(task) != previous_status:
                notify_task_status_change(task, request.user)
    except ValidationError as error:
        return _form_validation_error(error)
    return JsonResponse(_task_json(task))
