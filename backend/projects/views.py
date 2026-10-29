from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ProjectForm, ProjectMemberForm, ProjectUpdateForm
from .models import Project, ProjectMembership
from .permissions import (
    can_create_project,
    can_manage_project,
    ensure_project_owner_membership,
    manageable_project_ids_for,
    visible_projects_for,
)
from tasks.models import Task


def _manageable_project_or_403(user, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if not can_manage_project(user, project):
        raise PermissionDenied
    return project


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
            **{
                f"{status_value.lower()}_task_count": count
                for status_value, count in status_counts.items()
            },
        )
    )

    for project in projects:
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
def project_list(request):
    projects = visible_projects_for(request.user)
    context = {
        "projects": projects,
        "can_create_project": can_create_project(request.user),
        "manageable_project_ids": manageable_project_ids_for(request.user, projects),
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
                ProjectMembership.objects.create(
                    project=project,
                    user=form.cleaned_data["user"],
                    project_role=form.cleaned_data["project_role"],
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
        membership.delete()

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
