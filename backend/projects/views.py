from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from config.notifications import create_notifications
from tasks.models import Task

from .forms import (
    MilestoneForm,
    ProjectForm,
    ProjectMemberForm,
    ProjectSearchForm,
    ProjectUpdateForm,
    SprintForm,
)
from .models import Milestone, Project, ProjectMembership, Sprint, SprintTaskHistory
from .permissions import (
    can_create_project,
    can_manage_project,
    ensure_project_owner_membership,
    manageable_project_ids_for,
    visible_projects_for,
)


def _manageable_project_or_403(user, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if not can_manage_project(user, project):
        raise PermissionDenied
    return project


def _projects_with_task_progress(projects):
    return projects.annotate(
        task_count=Count("tasks", distinct=True),
        completed_task_count=Count(
            "tasks",
            filter=Q(tasks__status=Task.Status.DONE),
            distinct=True,
        ),
    )


@login_required
def dashboard(request):
    visible_projects = visible_projects_for(request.user)
    status_counts = {
        status_value: Count(
            "tasks",
            filter=Q(tasks__status=status_value),
        )
        for status_value, _ in Task.Status.choices
    }
    projects = list(
        visible_projects.annotate(
            total_task_count=Count("tasks", distinct=True),
            total_estimated_effort=Coalesce(
                Sum("tasks__estimated_effort"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            total_actual_effort=Coalesce(
                Sum("tasks__actual_effort"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            **{
                f"{status_value.lower()}_task_count": count
                for status_value, count in status_counts.items()
            },
        )
    )
    active_sprints = {
        sprint.project_id: sprint
        for sprint in Sprint.objects.filter(
            project_id__in=[project.pk for project in projects],
            status=Sprint.Status.ACTIVE,
        ).annotate(
            task_count=Count("tasks"),
            estimated_effort=Coalesce(
                Sum("tasks__estimated_effort"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            actual_effort=Coalesce(
                Sum("tasks__actual_effort"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
    }

    for project in projects:
        project.active_sprint = active_sprints.get(project.pk)
        project.status_breakdown = [
            {
                "value": status_value,
                "label": status_label,
                "count": getattr(project, f"{status_value.lower()}_task_count"),
            }
            for status_value, status_label in Task.Status.choices
        ]
        project.completed_task_count = getattr(
            project,
            f"{Task.Status.DONE.lower()}_task_count",
        )
        project.completion_percentage = (
            round(project.completed_task_count * 100 / project.total_task_count)
            if project.total_task_count
            else 0
        )

    visible_tasks = Task.objects.filter(project__in=visible_projects)
    assignee_distribution = list(
        visible_tasks.filter(assignee__isnull=False)
        .values("assignee_id", "assignee__full_name", "assignee__email")
        .annotate(task_count=Count("id"))
        .order_by("assignee__full_name", "assignee__email")
    )
    unassigned_task_count = visible_tasks.filter(assignee__isnull=True).count()
    if unassigned_task_count:
        assignee_distribution.append(
            {
                "assignee_id": None,
                "assignee__full_name": "Unassigned",
                "assignee__email": "",
                "task_count": unassigned_task_count,
            }
        )

    context = {
        "total_projects": len(projects),
        "active_projects": sum(
            project.status == Project.Status.ACTIVE for project in projects
        ),
        "total_tasks": visible_tasks.count(),
        "my_tasks": visible_tasks.filter(assignee=request.user).count(),
        "completed_tasks": visible_tasks.filter(status=Task.Status.DONE).count(),
        "projects": projects,
        "task_status_choices": Task.Status.choices,
        "assignee_distribution": assignee_distribution,
        "unassigned_task_count": unassigned_task_count,
        "can_create_project": can_create_project(request.user),
    }
    return render(request, "dashboard.html", context)


@login_required
def sprint_list(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    sprints = project.sprints.annotate(
        task_count=Count("tasks"),
        completed_task_count=Count(
            "tasks", filter=Q(tasks__status=Task.Status.DONE)
        ),
        estimated_effort=Coalesce(
            Sum("tasks__estimated_effort"),
            Value(0),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        actual_effort=Coalesce(
            Sum("tasks__actual_effort"),
            Value(0),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
    )
    milestones = project.milestones.annotate(
        task_count=Count("tasks"),
        completed_task_count=Count(
            "tasks", filter=Q(tasks__status=Task.Status.DONE)
        ),
    )
    for milestone in milestones:
        milestone.completion_percentage = (
            round(milestone.completed_task_count * 100 / milestone.task_count)
            if milestone.task_count
            else 0
        )
    return render(
        request,
        "sprint_list.html",
        {
            "project": project,
            "sprints": sprints,
            "milestones": milestones,
            "can_manage": can_manage_project(request.user, project),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def sprint_create(request, project_id):
    project = _managed_project_or_403(request.user, project_id)
    if request.method == "POST":
        form = SprintForm(request.POST, project=project)
        if form.is_valid():
            sprint = form.save(commit=False)
            sprint.created_by = request.user
            sprint.project = project
            sprint.save()
            messages.success(request, "Sprint created successfully.")
            return redirect("projects:sprint-detail", project_id=project.pk, sprint_id=sprint.pk)
    else:
        form = SprintForm(project=project)
    return render(
        request,
        "sprint_form.html",
        {
            "form": form,
            "project": project,
            "is_update": False,
            "page_heading": f"Create sprint | {project.name}",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def sprint_update(request, project_id, sprint_id):
    sprint = _managed_sprint(request.user, project_id, sprint_id)
    if request.method == "POST":
        form = SprintForm(request.POST, instance=sprint, project=sprint.project)
        if form.is_valid():
            form.save()
            messages.success(request, "Sprint updated successfully.")
            return redirect(
                "projects:sprint-detail",
                project_id=sprint.project_id,
                sprint_id=sprint.pk,
            )
    else:
        form = SprintForm(instance=sprint, project=sprint.project)
    return render(
        request,
        "sprint_form.html",
        {
            "form": form,
            "project": sprint.project,
            "sprint": sprint,
            "is_update": True,
            "page_heading": f"Edit {sprint.name} | {sprint.project.name}",
        },
    )


@login_required
def sprint_detail(request, project_id, sprint_id):
    project = _visible_project_or_404(request.user, project_id)
    sprint = get_object_or_404(project.sprints, pk=sprint_id)
    tasks = sprint.tasks.select_related("assignee", "created_by").prefetch_related("labels")
    return render(
        request,
        "sprint_detail.html",
        {
            "project": project,
            "sprint": sprint,
            "tasks": tasks,
            "can_manage": can_manage_project(request.user, project),
        },
    )


@login_required
@require_POST
def sprint_activate(request, project_id, sprint_id):
    sprint = _managed_sprint(request.user, project_id, sprint_id)
    if sprint.status != Sprint.Status.PLANNED:
        raise PermissionDenied("Only planned sprints can be activated.")
    if sprint.end_date < sprint.start_date:
        raise PermissionDenied("Sprint dates are invalid.")
    with transaction.atomic():
        sprint.status = Sprint.Status.ACTIVE
        sprint.save(update_fields=["status", "updated_at"])
    messages.success(request, "Sprint activated successfully.")
    return redirect("projects:sprint-detail", project_id=project_id, sprint_id=sprint_id)


@login_required
@require_POST
def sprint_close(request, project_id, sprint_id):
    sprint = _managed_sprint(request.user, project_id, sprint_id)
    if sprint.status != Sprint.Status.ACTIVE:
        raise PermissionDenied("Only active sprints can be closed.")
    destination_id = request.POST.get("carry_over_sprint")
    destination = None
    if destination_id:
        destination = get_object_or_404(
            sprint.project.sprints,
            pk=destination_id,
        )
        if destination.status not in (Sprint.Status.PLANNED, Sprint.Status.ACTIVE):
            raise PermissionDenied("Tasks can only be carried to an eligible sprint.")
        if destination.pk == sprint.pk:
            raise PermissionDenied("Tasks cannot be carried over to the same sprint.")

    with transaction.atomic():
        incomplete_tasks = list(
            sprint.tasks.exclude(status=Task.Status.DONE).select_for_update()
        )
        for task in incomplete_tasks:
            SprintTaskHistory.objects.create(
                task=task,
                sprint=sprint,
                carried_over=destination is not None,
                carried_over_to=destination,
                event_type="CARRY_OVER" if destination else "RETURN_TO_BACKLOG",
                carry_over_reason=request.POST.get("note", "").strip(),
                actor=request.user,
                carried_over_at=timezone.now(),
                task_status=task.status,
            )
            task.sprint = destination
            task.save(update_fields=["sprint", "updated_at"])
        sprint.status = Sprint.Status.COMPLETED
        sprint.save(update_fields=["status", "updated_at"])
    messages.success(request, "Sprint closed and incomplete tasks carried over.")
    return redirect("projects:sprint-detail", project_id=project_id, sprint_id=sprint_id)


@login_required
@require_http_methods(["GET", "POST"])
def milestone_create(request, project_id):
    project = _managed_project_or_403(request.user, project_id)
    if request.method == "POST":
        form = MilestoneForm(request.POST, project=project)
        if form.is_valid():
            form.save()
            messages.success(request, "Milestone created successfully.")
            return redirect("projects:sprint-list", project_id=project.pk)
    else:
        form = MilestoneForm(project=project)
    return render(
        request,
        "milestone_form.html",
        {"form": form, "project": project, "page_heading": f"Create milestone | {project.name}"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def milestone_update(request, project_id, milestone_id):
    project = _managed_project_or_403(request.user, project_id)
    milestone = get_object_or_404(project.milestones, pk=milestone_id)
    if request.method == "POST":
        form = MilestoneForm(request.POST, instance=milestone, project=project)
        if form.is_valid():
            form.save()
            messages.success(request, "Milestone updated successfully.")
            return redirect("projects:sprint-list", project_id=project.pk)
    else:
        form = MilestoneForm(instance=milestone, project=project)
    return render(
        request,
        "milestone_form.html",
        {
            "form": form,
            "project": project,
            "milestone": milestone,
            "page_heading": f"Edit {milestone.name} | {project.name}",
        },
    )


@login_required
def project_backlog(request, project_id):
    project = _visible_project_or_404(request.user, project_id)
    tasks = project.tasks.filter(sprint__isnull=True).select_related(
        "assignee", "created_by", "milestone"
    ).prefetch_related("labels")
    return render(
        request,
        "project_backlog.html",
        {"project": project, "tasks": tasks},
    )


def _visible_project_or_404(user, project_id):
    return get_object_or_404(visible_projects_for(user), pk=project_id)


def _require_project_manager(user, project):
    if not can_manage_project(user, project):
        raise PermissionDenied


def _managed_project_or_403(user, project_id):
    project = get_object_or_404(Project, pk=project_id)
    _require_project_manager(user, project)
    return project


def _managed_sprint(user, project_id, sprint_id):
    project = _managed_project_or_403(user, project_id)
    return get_object_or_404(project.sprints, pk=sprint_id)


@login_required
def project_list(request):
    projects = _projects_with_task_progress(visible_projects_for(request.user))
    search_form = ProjectSearchForm(request.GET)
    if search_form.is_valid():
        query = search_form.cleaned_data["q"]
        if query:
            projects = projects.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )
    else:
        projects = projects.none()

    manageable_project_ids = manageable_project_ids_for(request.user, projects)
    project_parameters = request.GET.copy()
    project_parameters.pop("page", None)
    project_query = project_parameters.urlencode()
    page_obj = Paginator(projects, 20).get_page(request.GET.get("page"))

    context = {
        "projects": page_obj,
        "page_obj": page_obj,
        "page_query": project_query,
        "search_form": search_form,
        "can_create_project": can_create_project(request.user),
        "manageable_project_ids": manageable_project_ids,
    }
    return render(request, "projects.html", context)


@login_required
def project_create(request):
    if not can_create_project(request.user):
        raise PermissionDenied

    if request.method == "POST":
        form = ProjectForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                project = form.save(commit=False)
                project.owner = request.user
                project.save()
                ProjectMembership.objects.create(
                    project=project,
                    user=request.user,
                    project_role=ProjectMembership.Role.PROJECT_MANAGER,
                )

            messages.success(request, "Project created successfully.")
            return redirect("projects:project-list")
    else:
        form = ProjectForm()

    context = {
        "form": form,
        "project_status_choices": form.fields["status"].choices,
    }
    return render(request, "project_form.html", context)


@login_required
def project_detail(request, project_id):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    can_manage = can_manage_project(request.user, project)
    memberships = project.memberships.select_related("user")
    member_form = (
        ProjectMemberForm(project=project, actor=request.user)
        if can_manage
        else None
    )
    context = {
        "project": project,
        "memberships": memberships,
        "can_manage_project": can_manage,
        "member_form": member_form,
    }
    return render(request, "project_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def project_update(request, project_id):
    project = _manageable_project_or_403(request.user, project_id)

    if request.method == "POST":
        form = ProjectUpdateForm(request.POST, instance=project)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                ensure_project_owner_membership(project)
            messages.success(request, "Project details updated successfully.")
            return redirect("projects:project-detail", project_id=project.pk)
    else:
        form = ProjectUpdateForm(instance=project)

    context = {
        "form": form,
        "project_status_choices": form.fields["status"].choices,
        "project": project,
        "is_update": True,
    }
    return render(request, "project_form.html", context)


@login_required
@require_POST
def project_add_member(request, project_id):
    project = _manageable_project_or_403(request.user, project_id)
    form = ProjectMemberForm(
        request.POST,
        project=project,
        actor=request.user,
    )

    if form.is_valid():
        try:
            with transaction.atomic():
                ensure_project_owner_membership(project)
                membership = ProjectMembership.objects.create(
                    project=project,
                    user=form.cleaned_data["user"],
                    project_role=form.cleaned_data["project_role"],
                )
                create_notifications(
                    title=f"Added to project: {project.name}",
                    message=(
                        f"You have been added to the project '{project.name}' "
                        f"as a {membership.get_project_role_display()}."
                    ),
                    recipients=[membership.user],
                )
        except IntegrityError:
            form.add_error("user", "This user is already a project member.")
        else:
            messages.success(request, "Project member added successfully.")
            return redirect("projects:project-detail", project_id=project.pk)

    return render(
        request,
        "project_detail.html",
        {
            "project": project,
            "memberships": project.memberships.select_related("user"),
            "can_manage_project": True,
            "member_form": form,
        },
    )


@login_required
@require_POST
def project_remove_member(request, project_id, membership_id):
    project = _manageable_project_or_403(request.user, project_id)
    membership = get_object_or_404(
        ProjectMembership,
        pk=membership_id,
        project=project,
    )

    if membership.user_id == project.owner_id:
        messages.error(request, "The project owner's Project Manager membership cannot be removed.")
        return redirect("projects:project-detail", project_id=project.pk)

    if (
        not request.user.is_admin
        and membership.project_role != ProjectMembership.Role.TEAM_MEMBER
    ):
        raise PermissionDenied

    with transaction.atomic():
        ensure_project_owner_membership(project)
        affected_user = membership.user
        removed_role = membership.get_project_role_display()
        membership.delete()
        create_notifications(
            title=f"Removed from project: {project.name}",
            message=(
                f"Your {removed_role} membership in the project "
                f"'{project.name}' has been removed."
            ),
            recipients=[affected_user],
        )

    messages.success(request, "Project member removed successfully.")
    return redirect("projects:project-detail", project_id=project.pk)


@login_required
@require_POST
def project_archive(request, project_id):
    project = _manageable_project_or_403(request.user, project_id)
    if project.status != Project.Status.ARCHIVED:
        project.status = Project.Status.ARCHIVED
        project.save(update_fields=["status", "updated_at"])
    messages.success(request, "Project archived successfully.")
    return redirect("projects:project-detail", project_id=project.pk)


@login_required
@require_http_methods(["GET", "POST"])
def project_delete(request, project_id):
    project = _manageable_project_or_403(request.user, project_id)

    if request.method == "POST":
        project_name = project.name
        project.delete()
        messages.success(request, f"{project_name} was deleted.")
        return redirect("projects:project-list")

    return render(request, "project_confirm_delete.html", {"project": project})
