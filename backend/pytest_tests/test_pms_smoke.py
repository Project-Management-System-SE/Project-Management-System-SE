"""Pytest-style examples that exercise core PMS behavior."""

import pytest
from django.urls import reverse

from accounts.models import User
from projects.models import Project, ProjectMembership
from projects.permissions import visible_projects_for
from tasks.models import Task


def create_user(email, username, full_name):
    return User.objects.create_user(
        email=email,
        username=username,
        full_name=full_name,
        password="pytest-password-123",
    )


def create_project_with_member():
    owner = create_user("pytest-owner@example.com", "pytest-owner", "Project Owner")
    member = create_user("pytest-member@example.com", "pytest-member", "Project Member")
    project = Project.objects.create(name="Pytest Demo Project", owner=owner)
    ProjectMembership.objects.create(
        project=project,
        user=owner,
        project_role=ProjectMembership.Role.PROJECT_MANAGER,
    )
    ProjectMembership.objects.create(
        project=project,
        user=member,
        project_role=ProjectMembership.Role.TEAM_MEMBER,
    )
    task = Task.objects.create(
        project=project,
        title="Pytest sample task",
        created_by=owner,
        assignee=member,
    )
    return owner, member, project, task


@pytest.mark.django_db
def test_user_password_is_hashed_and_authenticates():
    user = create_user("password@example.com", "password-user", "Password User")

    assert user.password != "pytest-password-123"
    assert user.check_password("pytest-password-123")
    assert not user.check_password("wrong-password")


@pytest.mark.django_db
def test_project_visibility_includes_member_but_excludes_outsider():
    _, member, project, _ = create_project_with_member()
    outsider = create_user("outsider@example.com", "outsider", "Outsider")

    assert visible_projects_for(member).filter(pk=project.pk).exists()
    assert not visible_projects_for(outsider).filter(pk=project.pk).exists()


@pytest.mark.django_db
def test_project_member_can_open_task_list(client):
    _, member, project, task = create_project_with_member()
    client.force_login(member)

    response = client.get(
        reverse("tasks:task-list", kwargs={"project_id": project.pk}),
        {"view": "list"},
    )

    assert response.status_code == 200
    assert task.title in response.content.decode()


@pytest.mark.django_db
def test_outsider_cannot_open_project_task_list(client):
    _, _, project, _ = create_project_with_member()
    outsider = create_user("outsider@example.com", "outsider", "Outsider")
    client.force_login(outsider)

    response = client.get(
        reverse("tasks:task-list", kwargs={"project_id": project.pk})
    )

    assert response.status_code == 404
