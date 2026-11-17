from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from projects.permissions import can_manage_project, visible_projects_for

from .forms import TaskCommentForm, TaskForm, TaskStatusForm
from .models import (
    Task,
    UserNotification,
    WorkflowState,
    WorkflowTransition,
)
from .notifications import (
    notify_task_assignment,
    notify_task_comment,
    notify_task_status_change,
)
from .permissions import can_create_task_in, can_edit_task
from .workflow import (
    allowed_status_transitions,
    set_task_workflow_status,
    task_status_for_workflow_state,
    workflow_choices_for,
    workflow_status_key,
)
from .workflow_forms import WorkflowConfigurationForm


@login_required
def task_list(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    tasks = list(
        project.tasks.select_related("assignee", "created_by")
        .select_related("workflow_state")
        .prefetch_related("labels")
        .order_by("-created_at")
    )
    can_manage_all_tasks = can_manage_project(request.user, project)
    board_choices = workflow_choices_for(project)
    columns = [
        {"value": value, "label": label, "tasks": []}
        for value, label in board_choices
    ]
    columns_by_status = {column["value"]: column for column in columns}
    for task in tasks:
        task.can_move = can_manage_all_tasks or (
            task.assignee_id == request.user.pk
            or task.created_by_id == request.user.pk
        )
        task.allowed_status_choices = [
            (value, label)
            for value, label in board_choices
            if value
            in allowed_status_transitions(workflow_status_key(task), project)
        ]
        current_status = workflow_status_key(task)
        if current_status not in columns_by_status:
            raise RuntimeError(
                f"Task {task.pk} has a status missing from project {project.pk}'s workflow."
            )
        columns_by_status[current_status]["tasks"].append(task)

    return render(
        request,
        "task_list.html",
        {
            "project": project,
            "tasks": tasks,
            "board_columns": columns,
            "can_create_task": can_create_task_in(request.user, project),
        },
    )


@login_required
def all_task_list(request):
    projects = visible_projects_for(request.user)
    tasks = (
        Task.objects.filter(project__in=projects)
        .select_related("project", "assignee", "created_by", "workflow_state")
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
                if task.assignee_id:
                    notify_task_assignment(task)
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
        project.tasks.select_related(
            "assignee",
            "created_by",
            "project",
            "workflow_state",
        ).prefetch_related("labels"),
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
            "status_form": TaskStatusForm(
                current_status=workflow_status_key(task),
                project=project,
                initial={"status": workflow_status_key(task)},
            ),
            "comments": task.comments.select_related("author"),
            "comment_form": TaskCommentForm(),
        },
    )


@login_required
def task_update(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(
        project.tasks.select_related(
            "assignee",
            "created_by",
            "project",
            "workflow_state",
        ).prefetch_related("labels"),
        pk=task_id,
    )
    if not can_edit_task(request.user, task):
        raise PermissionDenied("You do not have permission to edit this task.")

    previous_assignee_id = task.assignee_id
    previous_status = workflow_status_key(task)
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, project=project)
        if form.is_valid():
            with transaction.atomic():
                task = form.save()
                if task.assignee_id and task.assignee_id != previous_assignee_id:
                    notify_task_assignment(task)
                if workflow_status_key(task) != previous_status:
                    notify_task_status_change(task, request.user)
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
@require_http_methods(["GET", "POST"])
def task_delete(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(project.tasks, pk=task_id)
    if not can_edit_task(request.user, task):
        raise PermissionDenied("You do not have permission to delete this task.")

    if request.method == "POST":
        task_title = task.title
        task.delete()
        messages.success(request, f"Task '{task_title}' was deleted.")
        return redirect("tasks:task-list", project_id=project.pk)

    return render(
        request,
        "task_confirm_delete.html",
        {"project": project, "task": task},
    )


@login_required
@require_POST
def task_update_status(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(
        project.tasks.select_related("assignee", "created_by", "workflow_state"),
        pk=task_id,
    )
    if not can_edit_task(request.user, task):
        raise PermissionDenied("You do not have permission to update this task.")

    status_form = TaskStatusForm(
        request.POST,
        current_status=workflow_status_key(task),
        project=project,
    )
    if status_form.is_valid():
        previous_status = workflow_status_key(task)
        with transaction.atomic():
            set_task_workflow_status(
                task,
                status_form.cleaned_data["status"],
                project,
            )
            task.save()
            if workflow_status_key(task) != previous_status:
                notify_task_status_change(task, request.user)
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
            "comments": task.comments.select_related("author"),
            "comment_form": TaskCommentForm(),
        },
        status=400,
    )


@login_required
@require_http_methods(["GET", "POST"])
def workflow_configure(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    if not can_manage_project(request.user, project):
        raise PermissionDenied("You do not have permission to configure this workflow.")

    if request.method == "POST":
        form = WorkflowConfigurationForm(request.POST, project=project)
        if form.is_valid():
            with transaction.atomic():
                project.workflow_states.update(is_initial=False, is_final=False)
                for existing_state in project.workflow_states.all():
                    existing_state.name = f"__pending_{existing_state.key}__"
                    existing_state.save(update_fields=["name"])
                state_objects = {}
                for position, state_data in enumerate(form.workflow_states):
                    state, _ = WorkflowState.objects.update_or_create(
                        project=project,
                        key=state_data["key"],
                        defaults={
                            "name": state_data["name"],
                            "position": position,
                            "is_initial": state_data["is_initial"],
                            "is_final": state_data["is_final"],
                        },
                    )
                    state_objects[state.key] = state

                WorkflowTransition.objects.filter(
                    from_state__project=project
                ).delete()
                WorkflowTransition.objects.bulk_create(
                    [
                        WorkflowTransition(
                            from_state=state_objects[source],
                            to_state=state_objects[target],
                        )
                        for source, target in form.workflow_transitions
                    ]
                )
                project.workflow_states.exclude(
                    key__in=state_objects
                ).delete()

                for state_key, state in state_objects.items():
                    tasks = project.tasks.filter(
                        Q(workflow_state=state)
                        | Q(workflow_state__isnull=True, status=state_key)
                    )
                    for task in tasks.select_related("workflow_state"):
                        task.workflow_state = state
                        task.status = task_status_for_workflow_state(state)
                        task.save(
                            update_fields=[
                                "workflow_state",
                                "status",
                                "completed_at",
                                "updated_at",
                            ]
                        )

            messages.success(request, "Project workflow updated successfully.")
            return redirect("projects:project-detail", project_id=project.pk)
    else:
        form = WorkflowConfigurationForm(project=project)

    return render(
        request,
        "tasks/workflow_form.html",
        {"project": project, "form": form},
    )


@login_required
@require_POST
def task_add_comment(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(
        project.tasks.select_related("assignee", "created_by", "project"),
        pk=task_id,
    )
    form = TaskCommentForm(request.POST)

    if form.is_valid():
        with transaction.atomic():
            comment = form.save(commit=False)
            comment.task = task
            comment.author = request.user
            comment.save()
            notify_task_comment(task, comment)
        messages.success(request, "Comment added.")
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
            "can_edit_task": can_edit_task(request.user, task),
            "can_update_status": can_edit_task(request.user, task),
            "status_form": TaskStatusForm(
                current_status=workflow_status_key(task),
                project=project,
                initial={"status": workflow_status_key(task)},
            ),
            "comments": task.comments.select_related("author"),
            "comment_form": form,
        },
        status=400,
    )


@login_required
def notification_inbox(request):
    notifications = request.user.notifications.all()
    return render(
        request,
        "notifications.html",
        {
            "notifications": notifications,
            "unread_count": notifications.filter(read_at__isnull=True).count(),
        },
    )


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    notification = get_object_or_404(
        UserNotification,
        pk=notification_id,
        recipient=request.user,
    )
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])

    return redirect("tasks:notification-inbox")
