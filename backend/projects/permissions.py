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


def visible_projects_for(user):
    projects = Project.objects.select_related("owner").order_by("-created_at")

    if not user.is_authenticated:
        return projects.none()

    if user.is_admin:
        return projects

    return projects.filter(
        Q(owner=user) | Q(memberships__user=user)
    ).distinct()
