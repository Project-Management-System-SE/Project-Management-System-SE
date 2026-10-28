from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from projects.permissions import visible_projects_for

from .forms import TaskForm
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

    context = {
        "project": project,
        "tasks": tasks,
        "can_create_task": can_create_task_in(request.user, project),
    }
    return render(request, "task_list.html", context)


@login_required
def task_create(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    if not can_create_task_in(request.user, project):
        raise PermissionDenied("You do not have permission to create tasks in this project.")

    save_error = None
    if request.method == "POST":
        form = TaskForm(request.POST, project=project)
        if form.is_valid():
            try:
                with transaction.atomic():
                    task = form.save(commit=False)
                    task.project = project
                    task.created_by = request.user
                    task.save()
                    form.save_m2m()
                messages.success(request, f"Task '{task.title}' created successfully.")
                return redirect("tasks:task-detail", project_id=project.pk, task_id=task.pk)
            except Exception:
                save_error = "Could not save the task. Please try again."
    else:
        form = TaskForm(project=project)

    context = {
        "form": form,
        "project": project,
        "page_heading": f"Create Task | {project.name}",
        "form_heading": "Create task",
        "form_intro": f"Add a new task to {project.name}.",
        "submit_label": "Create task",
        "cancel_url": reverse("projects:project-detail", kwargs={"project_id": project.pk}),
        "cancel_label": "Cancel",
        "save_error": save_error,
    }
    return render(request, "task_form.html", context)


@login_required
def task_detail(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(
        project.tasks.select_related("assignee", "created_by", "project").prefetch_related("labels"),
        pk=task_id,
    )

    context = {
        "project": project,
        "task": task,
        "can_edit_task": can_edit_task(request.user, task),
    }
    return render(request, "task_detail.html", context)


@login_required
def task_update(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(
        project.tasks.select_related("assignee", "created_by", "project").prefetch_related("labels"),
        pk=task_id,
    )
    if not can_edit_task(request.user, task):
        raise PermissionDenied("You do not have permission to edit this task.")

    save_error = None
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, project=project)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                messages.success(request, f"Task '{task.title}' updated successfully.")
                return redirect("tasks:task-detail", project_id=project.pk, task_id=task.pk)
            except Exception:
                save_error = "Could not save changes to the task. Please try again."
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
        "cancel_url": reverse("tasks:task-detail", kwargs={"project_id": project.pk, "task_id": task.pk}),
        "cancel_label": "Cancel",
        "save_error": save_error,
    }
    return render(request, "task_form.html", context)
