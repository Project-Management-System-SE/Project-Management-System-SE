from functools import wraps

from django.db.models import Count, Q
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from projects.models import Project
from projects.permissions import visible_projects_for

from .forms import TaskFilterForm
from .models import Task
from .workflow import workflow_choices_for, workflow_status_key


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
@_api_methods("GET")
def api_project_task_list(request, project_id):
    project = _visible_project_or_404(request.user, project_id)
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
@_api_methods("GET")
def api_project_task_detail(request, project_id, task_id):
    project = _visible_project_or_404(request.user, project_id)
    task = get_object_or_404(_project_tasks(project), pk=task_id)
    return JsonResponse(_task_json(task))
