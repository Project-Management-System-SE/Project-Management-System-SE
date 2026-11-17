import logging
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from projects.permissions import can_manage_project, visible_projects_for

from .audit import changes_from_form, record_audit
from .forms import (
    TaskAttachmentForm,
    TaskCommentForm,
    TaskFilterForm,
    TaskForm,
    TaskStatusForm,
)
from .models import (
    AuditLog,
    Task,
    TaskAttachment,
    TaskComment,
    UserNotification,
    WorkflowState,
    WorkflowTransition,
)
from .notifications import (
    notify_task_assignment,
    notify_task_comment,
    notify_task_status_change,
)
from .permissions import can_create_task_in, can_edit_task, can_view_tasks_for
from .workflow import (
    allowed_status_transitions,
    set_task_workflow_status,
    task_status_for_workflow_state,
    workflow_choices_for,
    workflow_status_key,
    workflow_states_for,
)
from .workflow_forms import WorkflowConfigurationForm

logger = logging.getLogger(__name__)


def _task_status_request_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        expects_json = "application/json" in request.headers.get("Accept", "")
        if not request.user.is_authenticated:
            if expects_json:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Your session has expired. Sign in and try again.",
                    },
                    status=401,
                )
            return redirect_to_login(request.get_full_path())

        if request.method != "POST":
            if expects_json:
                return JsonResponse(
                    {"success": False, "error": "POST requests are required."},
                    status=405,
                )
            return HttpResponseNotAllowed(["POST"])

        return view(request, *args, **kwargs)

    return wrapped


def _get_visible_task(user, project_id, task_id):
    task = get_object_or_404(
        Task.objects.select_related(
            "project",
            "assignee",
            "created_by",
            "sprint",
            "milestone",
            "workflow_state",
        ).prefetch_related("labels"),
        pk=task_id,
        project_id=project_id,
    )
    if not can_view_tasks_for(user, task.project):
        raise Http404
    return task


def _task_detail_context(
    request,
    task,
    comment_form=None,
    attachment_form=None,
    status_form=None,
):
    can_edit = can_edit_task(request.user, task)
    return {
        "project": task.project,
        "task": task,
        "can_edit_task": can_edit,
        "can_manage_project": can_manage_project(request.user, task.project),
        "can_update_status": can_edit,
        "status_form": (
            status_form
            if status_form is not None
            else TaskStatusForm(
                current_status=workflow_status_key(task),
                project=task.project,
                initial={"status": workflow_status_key(task)},
            )
        ),
        "comments": task.comments.select_related("author").order_by("created_at", "pk"),
        "activity": task.audit_log_entries.select_related("actor").order_by(
            "timestamp", "pk"
        ),
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


def _render_task_detail(
    request,
    task,
    comment_form=None,
    attachment_form=None,
    status_form=None,
):
    return render(
        request,
        "task_detail.html",
        _task_detail_context(
            request,
            task,
            comment_form,
            attachment_form,
            status_form,
        ),
    )


@login_required
def task_list(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    tasks = (
        project.tasks.select_related(
            "assignee",
            "created_by",
            "sprint",
            "milestone",
            "workflow_state",
        )
        .prefetch_related("labels")
        .order_by("-created_at")
    )
    view_mode = "list" if request.GET.get("view") == "list" else "board"
    filter_form = TaskFilterForm(request.GET, project=project)
    board_choices = workflow_choices_for(project)
    filter_form.fields["status"].choices = (("", "All statuses"), *board_choices)
    if filter_form.is_valid():
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
            if workflow_states_for(project):
                tasks = tasks.filter(workflow_state__key=filters["status"])
            else:
                tasks = tasks.filter(status=filters["status"])
        if filters["label"]:
            tasks = tasks.filter(labels=filters["label"])
        if filters["sprint"]:
            tasks = tasks.filter(sprint=filters["sprint"])
    else:
        tasks = tasks.none()

    filter_parameters = request.GET.copy()
    filter_parameters.pop("view", None)
    filter_parameters.pop("page", None)
    filter_query = filter_parameters.urlencode()
    task_columns = []
    page_obj = None
    if view_mode == "board":
        task_items = list(tasks)
        task_columns = [
            {"value": value, "status": value, "label": label, "tasks": []}
            for value, label in board_choices
        ]
        columns_by_status = {column["value"]: column for column in task_columns}
        for task in task_items:
            current_status = workflow_status_key(task)
            if current_status not in columns_by_status:
                raise RuntimeError(
                    f"Task {task.pk} has a status missing from project "
                    f"{project.pk}'s workflow."
                )
            task.can_move = can_edit_task(request.user, task)
            task.can_update_status = task.can_move
            task.allowed_status_choices = [
                (value, label)
                for value, label in board_choices
                if value in allowed_status_transitions(current_status, project)
            ]
            task.board_status_key = current_status
            task.board_status_label = task.workflow_state.name if task.workflow_state_id else task.get_status_display()
            task_columns_by_status = columns_by_status[current_status]
            task_columns_by_status["tasks"].append(task)
            if task.can_update_status:
                task.status_form = TaskStatusForm(
                    current_status=current_status,
                    project=project,
                    initial={"status": current_status},
                )
                task.status_form.fields["status"].widget.attrs.update(
                    {
                        "id": f"task-{task.pk}-status",
                        "aria-label": f"Status for {task.title}",
                    }
                )
    else:
        page_obj = Paginator(tasks, 20).get_page(request.GET.get("page"))
        tasks = page_obj.object_list

    context = {
        "project": project,
        "tasks": tasks,
        "view_mode": view_mode,
        "task_columns": task_columns,
        "filter_form": filter_form,
        "filter_query": filter_query,
        "page_obj": page_obj,
        "board_columns": task_columns,
        "can_create_task": can_create_task_in(request.user, project),
    }
    return render(request, "task_list.html", context)


@login_required
def all_task_list(request):
    projects = visible_projects_for(request.user)
    tasks = (
        Task.objects.filter(project__in=projects)
        .select_related(
            "project",
            "assignee",
            "created_by",
            "workflow_state",
            "sprint",
            "milestone",
        )
        .prefetch_related("labels")
    )
    return render(request, "tasks/task_list.html", {"tasks": tasks})


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

    if request.method == "POST":
        form = TaskForm(request.POST, project=project)
        if form.is_valid():
            with transaction.atomic():
                task = form.save(commit=False)
                task.project = project
                task.created_by = request.user
                task.save()
                form.save_m2m()
                record_audit(request.user, AuditLog.Action.CREATE, task)
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
                notify_task_comment(task, comment)
        except DatabaseError:
            logger.exception("Could not save comment for task %s", task.pk)
            form.add_error(None, "Could not save your comment. Please try again.")
        else:
            messages.success(request, "Comment added.")
            return redirect("tasks:task-detail", project_id=project_id, task_id=task_id)

    return _render_task_detail(request, task, comment_form=form)


task_add_comment = task_comment_create


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
        project.tasks.select_related(
            "assignee",
            "created_by",
            "project",
            "workflow_state",
            "sprint",
            "milestone",
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


@_task_status_request_required
def task_update_status(request, project_id, task_id):
    expects_json = "application/json" in request.headers.get("Accept", "")
    try:
        project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
        task = get_object_or_404(
            project.tasks.select_related(
                "assignee",
                "created_by",
                "workflow_state",
            ),
            pk=task_id,
        )
    except Http404:
        if expects_json:
            return JsonResponse(
                {"success": False, "error": "This task is not available."},
                status=404,
            )
        raise

    if not can_edit_task(request.user, task):
        if expects_json:
            return JsonResponse(
                {
                    "success": False,
                    "error": "You do not have permission to update this task.",
                },
                status=403,
            )
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
            current_status = workflow_status_key(task)
            if current_status != previous_status:
                record_audit(
                    request.user,
                    AuditLog.Action.UPDATE,
                    task,
                    changes={
                        "status": {
                            "from": previous_status,
                            "to": current_status,
                        }
                    },
                )
                notify_task_status_change(task, request.user)
        if expects_json:
            status_display = (
                task.workflow_state.name
                if task.workflow_state_id
                else task.get_status_display()
            )
            return JsonResponse(
                {
                    "success": True,
                    "status": workflow_status_key(task),
                    "status_display": status_display,
                    "message": "Task status updated.",
                }
            )
        messages.success(request, "Task status updated.")
        return redirect(
            "tasks:task-detail",
            project_id=project.pk,
            task_id=task.pk,
        )

    if expects_json:
        return JsonResponse(
            {
                "success": False,
                "error": status_form.errors.get(
                    "status",
                    ["Enter a valid status."],
                )[0],
            },
            status=400,
        )

    return render(
        request,
        "task_detail.html",
        _task_detail_context(request, task, status_form=status_form),
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
                notify_task_comment(task, comment)
        except DatabaseError:
            logger.exception("Could not save comment for task %s", task.pk)
            form.add_error(None, "Could not save your comment. Please try again.")
        else:
            messages.success(request, "Comment added.")
            return redirect("tasks:task-detail", project_id=project_id, task_id=task_id)

    return render(
        request,
        "task_detail.html",
        _task_detail_context(request, task, comment_form=form),
    )


task_add_comment = task_comment_create


@login_required
@require_http_methods(["GET", "POST"])
def task_delete(request, project_id, task_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    task = get_object_or_404(project.tasks, pk=task_id)
    if not can_manage_project(request.user, project):
        raise PermissionDenied("You do not have permission to delete this task.")

    if request.method == "POST":
        task_name = task.title
        with transaction.atomic():
            record_audit(request.user, AuditLog.Action.DELETE, task)
            task.delete()
        messages.success(request, f"{task_name} was deleted.")
        return redirect("tasks:task-list", project_id=project.pk)

    return render(request, "task_confirm_delete.html", {"project": project, "task": task})


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
