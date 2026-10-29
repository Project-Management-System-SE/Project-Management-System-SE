from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from projects.permissions import visible_projects_for

from .forms import TaskForm, TaskStatusForm
from .models import Task
from .permissions import can_create_task_in, can_edit_task


@login_required
def task_list(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    tasks = (
        project.tasks.select_related("assignee", "created_by")
        .prefetch_related("labels")
        .order_by("-created_at")
    )

    return render(
        request,
        "task_list.html",
        {
            "project": project,
            "tasks": tasks,
            "can_create_task": can_create_task_in(request.user, project),
        },
    )


@login_required
def all_task_list(request):
    projects = visible_projects_for(request.user)
    tasks = (
        Task.objects.filter(project__in=projects)
        .select_related("project", "assignee", "created_by")
        .prefetch_related("labels")
    )
    return render(request, "tasks/task_list.html", {"tasks": tasks})


@login_required
def task_create(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    if not can_create_task_in(request.user, project):
        raise PermissionDenied("You do not have permission to create tasks in this project.")

    if request.method == "POST":
        form = TaskForm(request.POST, project=project)
        if form.is_valid():
            with transaction.atomic():
                task = form.save(commit=False)
                task.project = project
                task.created_by = request.user
                task.save()
                form.save_m2m()
            messages.success(request, f"Task '{task.title}' created successfully.")
            return redirect(
                "tasks:task-detail",
                project_id=project.pk,
                task_id=task.pk,
            )
    else:
        form = TaskForm(project=project)

    context = {
        "form": form,
        "project": project,
        "page_heading": f"Create Task | {project.name}",
        "form_heading": "Create task",
        "form_intro": f"Add a new task to {project.name}.",
        "submit_label": "Create task",
        "cancel_url": reverse(
            "projects:project-detail",
            kwargs={"project_id": project.pk},
        ),
        "cancel_label": "Cancel",
    }
    return render(request, "task_form.html", context)


@login_required
def task_detail(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(
        project.tasks.select_related("assignee", "created_by", "project").prefetch_related("labels"),
        pk=task_id,
    )
    can_edit = can_edit_task(request.user, task)

    return render(
        request,
        "task_detail.html",
        {
            "project": project,
            "task": task,
            "can_edit_task": can_edit,
            "can_update_status": can_edit,
            "status_form": TaskStatusForm(initial={"status": task.status}),
        },
    )


@login_required
def task_update(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(
        project.tasks.select_related("assignee", "created_by", "project").prefetch_related("labels"),
        pk=task_id,
    )
    if not can_edit_task(request.user, task):
        raise PermissionDenied("You do not have permission to edit this task.")

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, project=project)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, f"Task '{task.title}' updated successfully.")
            return redirect(
                "tasks:task-detail",
                project_id=project.pk,
                task_id=task.pk,
            )
    else:
        form = TaskForm(instance=task, project=project)

    context = {
        "form": form,
        "project": project,
        "task": task,
        "page_heading": f"Edit {task.title} | {project.name}",
        "form_heading": "Edit task",
        "form_intro": f"Update task details for {task.title}.",
        "submit_label": "Save changes",
        "cancel_url": reverse(
            "tasks:task-detail",
            kwargs={"project_id": project.pk, "task_id": task.pk},
        ),
        "cancel_label": "Cancel",
    }
    return render(request, "task_form.html", context)


@login_required
@require_POST
def task_update_status(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(project.tasks.select_related("assignee", "created_by"), pk=task_id)
    if not can_edit_task(request.user, task):
        raise PermissionDenied("You do not have permission to update this task.")

    status_form = TaskStatusForm(request.POST)
    if status_form.is_valid():
        task.status = status_form.cleaned_data["status"]
        task.save()
        messages.success(request, "Task status updated.")
        return redirect(
            "tasks:task-detail",
            project_id=project.pk,
            task_id=task.pk,
        )

    return render(
        request,
        "task_detail.html",
        {
            "project": project,
            "task": task,
            "can_edit_task": True,
            "can_update_status": True,
            "status_form": status_form,
        },
        status=400,
    )
