import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from projects.permissions import visible_projects_for

from .forms import TaskAttachmentForm, TaskCommentForm, TaskForm
from .models import Task, TaskAttachment
from .permissions import can_create_task_in, can_edit_task, can_view_tasks_for

logger = logging.getLogger(__name__)


def _get_visible_task(user, project_id, task_id):
    task = get_object_or_404(
        Task.objects.select_related("project", "assignee", "created_by")
        .prefetch_related("labels"),
        pk=task_id,
        project_id=project_id,
    )
    if not can_view_tasks_for(user, task.project):
        raise Http404
    return task


def _task_detail_context(request, task, comment_form=None, attachment_form=None):
    return {
        "project": task.project,
        "task": task,
        "can_edit_task": can_edit_task(request.user, task),
        "comments": task.comments.select_related("author").order_by("created_at", "pk"),
        "attachments": task.attachments.select_related("uploaded_by").order_by(
            "created_at", "pk"
        ),
        "comment_form": comment_form if comment_form is not None else TaskCommentForm(),
        "attachment_form": (
            attachment_form
            if attachment_form is not None
            else TaskAttachmentForm()
        ),
    }


def _render_task_detail(request, task, comment_form=None, attachment_form=None):
    return render(
        request,
        "task_detail.html",
        _task_detail_context(request, task, comment_form, attachment_form),
    )


@login_required
def task_list(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    tasks = (
        project.tasks.select_related("assignee", "created_by")
        .prefetch_related("labels")
        .order_by("-created_at")
    )
    view_mode = "board" if request.GET.get("view") == "board" else "list"
    task_columns = []
    if view_mode == "board":
        task_items = list(tasks)
        task_columns = [
            {
                "status": status,
                "label": label,
                "tasks": [task for task in task_items if task.status == status],
            }
            for status, label in Task.Status.choices
        ]

    context = {
        "project": project,
        "tasks": tasks,
        "view_mode": view_mode,
        "task_columns": task_columns,
        "can_create_task": can_create_task_in(request.user, project),
    }
    return render(request, "task_list.html", context)


@login_required
def my_tasks(request):
    tasks = (
        Task.objects.filter(
            project__in=visible_projects_for(request.user),
            assignee=request.user,
        )
        .select_related("project", "assignee", "created_by")
        .prefetch_related("labels")
        .order_by("due_date", "-created_at")
    )
    return render(request, "my_tasks.html", {"tasks": tasks})


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
    task = _get_visible_task(request.user, project_id, task_id)
    return _render_task_detail(request, task)


@login_required
def task_comment_create(request, project_id, task_id):
    task = _get_visible_task(request.user, project_id, task_id)
    if request.method != "POST":
        return redirect("tasks:task-detail", project_id=project_id, task_id=task_id)

    form = TaskCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        try:
            with transaction.atomic():
                comment.save()
        except DatabaseError:
            logger.exception("Could not save comment for task %s", task.pk)
            form.add_error(None, "Could not save your comment. Please try again.")
        else:
            messages.success(request, "Comment added.")
            return redirect("tasks:task-detail", project_id=project_id, task_id=task_id)

    return _render_task_detail(request, task, comment_form=form)


@login_required
def task_attachment_upload(request, project_id, task_id):
    task = _get_visible_task(request.user, project_id, task_id)
    if request.method != "POST":
        return redirect("tasks:task-detail", project_id=project_id, task_id=task_id)

    form = TaskAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.task = task
        attachment.uploaded_by = request.user
        attachment.original_filename = form.cleaned_data["file"].name
        original_file_name = attachment.file.name
        try:
            with transaction.atomic():
                attachment.save()
        except (DatabaseError, OSError):
            logger.exception("Could not save attachment for task %s", task.pk)
            if attachment.file.name != original_file_name:
                try:
                    attachment.file.delete(save=False)
                except OSError:
                    logger.exception(
                        "Could not clean up attachment file for task %s", task.pk
                    )
            form.add_error(None, "Could not save the attachment. Please try again.")
        else:
            messages.success(request, "Attachment uploaded.")
            return redirect("tasks:task-detail", project_id=project_id, task_id=task_id)

    return _render_task_detail(request, task, attachment_form=form)


@login_required
def task_attachment_download(request, project_id, task_id, attachment_id):
    task = _get_visible_task(request.user, project_id, task_id)
    attachment = get_object_or_404(task.attachments, pk=attachment_id)
    try:
        attachment_file = attachment.file.open("rb")
    except OSError:
        logger.exception("Could not open attachment %s for task %s", attachment.pk, task.pk)
        raise Http404("The requested attachment is unavailable.") from None

    response = FileResponse(
        attachment_file,
        as_attachment=True,
        filename=attachment.original_filename,
        content_type="application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


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
