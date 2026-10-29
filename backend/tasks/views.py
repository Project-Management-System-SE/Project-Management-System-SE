from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from projects.models import ProjectMembership
from projects.permissions import visible_projects_for

from .forms import TaskStatusForm
from .models import Task


def _can_update_task(user, task):
    return (
        user.is_admin
        or task.project.owner_id == user.pk
        or ProjectMembership.objects.filter(
            project=task.project,
            user=user,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        ).exists()
        or task.assignee_id == user.pk
    )


def _visible_task_or_404(user, project_id, task_id):
    return get_object_or_404(
        Task.objects.select_related("project", "assignee").filter(
            project__in=visible_projects_for(user)
        ),
        pk=task_id,
        project_id=project_id,
    )


@login_required
def task_list(request, project_id=None):
    projects = visible_projects_for(request.user)
    tasks = Task.objects.filter(project__in=projects).select_related(
        "project",
        "assignee",
    )
    selected_project = None

    if project_id is not None:
        selected_project = get_object_or_404(projects, pk=project_id)
        tasks = tasks.filter(project=selected_project)

    return render(
        request,
        "tasks/task_list.html",
        {
            "tasks": tasks,
            "selected_project": selected_project,
        },
    )


@login_required
def task_detail(request, project_id, task_id):
    task = _visible_task_or_404(request.user, project_id, task_id)
    can_update_status = _can_update_task(request.user, task)
    status_form = TaskStatusForm(initial={"status": task.status})

    return render(
        request,
        "tasks/task_detail.html",
        {
            "task": task,
            "can_update_status": can_update_status,
            "status_form": status_form,
        },
    )


@login_required
@require_POST
def task_update_status(request, project_id, task_id):
    task = _visible_task_or_404(request.user, project_id, task_id)
    if not _can_update_task(request.user, task):
        raise PermissionDenied

    status_form = TaskStatusForm(request.POST)
    if status_form.is_valid():
        task.status = status_form.cleaned_data["status"]
        task.save(update_fields=["status", "updated_at"])
        messages.success(request, "Task status updated.")
        return redirect(
            "tasks:task-detail",
            project_id=task.project_id,
            task_id=task.pk,
        )

    return render(
        request,
        "tasks/task_detail.html",
        {
            "task": task,
            "can_update_status": True,
            "status_form": status_form,
        },
        status=400,
    )
