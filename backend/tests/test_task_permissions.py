from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Project, ProjectMembership
from tasks.models import Task
from tasks.permissions import (
    can_create_task_in,
    can_delete_task,
    can_edit_task,
    can_reassign_task,
    can_view_tasks_for,
)

User = get_user_model()


class TaskPermissionsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="proj_owner",
            email="owner@example.com",
            full_name="Project Owner",
            password="password123",
        )
        self.pm = User.objects.create_user(
            username="proj_pm",
            email="pm@example.com",
            full_name="Project Manager",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="team_member",
            email="member@example.com",
            full_name="Team Member",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            full_name="External User",
            password="password123",
        )
        self.project = Project.objects.create(
            name="Security Test Project",
            owner=self.owner,
            status=Project.Status.ACTIVE,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.pm,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.task = Task.objects.create(
            title="Assigned Task",
            project=self.project,
            created_by=self.owner,
            assignee=self.member,
            status=Task.Status.TODO,
        )

    def test_view_tasks_permissions(self):
        self.assertTrue(can_view_tasks_for(self.owner, self.project))
        self.assertTrue(can_view_tasks_for(self.pm, self.project))
        self.assertTrue(can_view_tasks_for(self.member, self.project))
        self.assertFalse(can_view_tasks_for(self.outsider, self.project))

    def test_create_task_permissions(self):
        self.assertTrue(can_create_task_in(self.owner, self.project))
        self.assertTrue(can_create_task_in(self.pm, self.project))
        self.assertFalse(can_create_task_in(self.member, self.project))
        self.assertFalse(can_create_task_in(self.outsider, self.project))

    def test_edit_task_permissions(self):
        self.assertTrue(can_edit_task(self.owner, self.task))
        self.assertTrue(can_edit_task(self.pm, self.task))
        self.assertTrue(can_edit_task(self.member, self.task))
        self.assertFalse(can_edit_task(self.outsider, self.task))

    def test_reassign_task_permissions(self):
        self.assertTrue(can_reassign_task(self.owner, self.task))
        self.assertTrue(can_reassign_task(self.pm, self.task))
        self.assertFalse(can_reassign_task(self.member, self.task))
        self.assertFalse(can_reassign_task(self.outsider, self.task))

    def test_delete_task_permissions(self):
        self.assertTrue(can_delete_task(self.owner, self.task))
        self.assertTrue(can_delete_task(self.pm, self.task))
        self.assertFalse(can_delete_task(self.member, self.task))
        self.assertFalse(can_delete_task(self.outsider, self.task))
