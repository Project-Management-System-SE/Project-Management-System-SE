import datetime
from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Project, ProjectMembership
from tasks.forms import TaskForm
from tasks.models import Task

User = get_user_model()


class TaskValidationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner_val",
            email="owner_val@example.com",
            full_name="Owner Val",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="member_val",
            email="member_val@example.com",
            full_name="Member Val",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="outsider_val",
            email="outsider_val@example.com",
            full_name="Outsider Val",
            password="password123",
        )
        today = datetime.date.today()
        self.project = Project.objects.create(
            name="Validation Test Project",
            owner=self.owner,
            status=Project.Status.ACTIVE,
            start_date=today,
            due_date=today + datetime.timedelta(days=30),
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )

    def test_task_title_min_length(self):
        form = TaskForm(
            data={"title": "ab", "priority": Task.Priority.MEDIUM, "status": Task.Status.TODO},
            project=self.project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_task_title_xss_rejection(self):
        form = TaskForm(
            data={"title": "<script>alert(1)</script>", "priority": Task.Priority.MEDIUM, "status": Task.Status.TODO},
            project=self.project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_task_due_date_before_project_start(self):
        yesterday = self.project.start_date - datetime.timedelta(days=1)
        form = TaskForm(
            data={
                "title": "Valid Task Title",
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.TODO,
                "due_date": yesterday,
            },
            project=self.project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("due_date", form.errors)

    def test_assignee_outside_project_rejected(self):
        form = TaskForm(
            data={
                "title": "Valid Task Title",
                "priority": Task.Priority.HIGH,
                "status": Task.Status.TODO,
                "assignee": self.outsider.pk,
            },
            project=self.project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("assignee", form.errors)

    def test_valid_member_assignment_accepted(self):
        form = TaskForm(
            data={
                "title": "Valid Task Title",
                "priority": Task.Priority.HIGH,
                "status": Task.Status.TODO,
                "assignee": self.member.pk,
            },
            project=self.project,
        )
        self.assertTrue(form.is_valid(), form.errors)
