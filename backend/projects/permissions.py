from django.db.models import Q

from .models import Project, ProjectMembership


def can_create_project(user):
    if not user.is_authenticated:
        return False

    if user.is_admin:
        return True

    return user.project_memberships.filter(
        project_role=ProjectMembership.Role.PROJECT_MANAGER
    ).exists()


def can_manage_project(user, project):
    if not user.is_authenticated:
        return False

    return (
        user.is_admin
        or project.owner_id == user.pk
        or ProjectMembership.objects.filter(
            project=project,
            user=user,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        ).exists()
    )


def manageable_project_ids_for(user, projects):
    if not user.is_authenticated:
        return set()

    if user.is_admin:
        return set(projects.values_list("id", flat=True))

    return set(
        ProjectMembership.objects.filter(
            project__in=projects,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        .values_list("project_id", flat=True)
    ) | set(projects.filter(owner=user).values_list("id", flat=True))


def ensure_project_owner_membership(project):
    ProjectMembership.objects.update_or_create(
        project=project,
        user=project.owner,
        defaults={"project_role": ProjectMembership.Role.PROJECT_MANAGER},
    )


def visible_projects_for(user):
    projects = Project.objects.select_related("owner").order_by("-created_at")

    if not user.is_authenticated:
        return projects.none()

    if user.is_admin:
        return projects

    return projects.filter(
        Q(owner=user) | Q(memberships__user=user)
    ).distinct()
