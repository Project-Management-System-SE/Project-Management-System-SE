from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from projects.models import Project, ProjectMembership, Sprint
from tasks.models import Task, TaskLabel


class ProjectTaskApiReadTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="test-pass-123",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Team Member",
            password="test-pass-123",
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com",
            username="outsider",
            full_name="Outsider",
            password="test-pass-123",
        )
        self.project = Project.objects.create(name="API project", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.sprint = Sprint.objects.create(
            project=self.project,
            name="API sprint",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
        )
        self.label = TaskLabel.objects.create(project=self.project, name="backend")
        self.task = Task.objects.create(
            project=self.project,
            sprint=self.sprint,
            title="API task",
            description="Read-only task details",
            created_by=self.owner,
            assignee=self.member,
            priority=Task.Priority.HIGH,
            estimated_effort=Decimal("2.50"),
        )
        self.task.labels.add(self.label)

    def test_anonymous_api_request_returns_json_401(self):
        response = self.client.get(reverse("api-project-list"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Authentication is required."})

    def test_project_list_is_scoped_to_visible_projects(self):
        Project.objects.create(name="Private", owner=self.outsider)
        self.client.force_login(self.member)

        response = self.client.get(reverse("api-project-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["id"], self.project.pk)

    def test_task_list_supports_combined_filters_and_serializes_task_fields(self):
        self.client.force_login(self.member)

        response = self.client.get(
            reverse("api-project-task-list", args=[self.project.pk]),
            {
                "q": "API",
                "assignee": self.member.pk,
                "priority": Task.Priority.HIGH,
                "sprint": self.sprint.pk,
                "label": self.label.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], self.task.pk)
        self.assertEqual(result[0]["estimated_effort_hours"], "2.50")
        self.assertEqual(result[0]["labels"], ["backend"])
        self.assertEqual(result[0]["sprint"]["id"], self.sprint.pk)

    def test_task_list_rejects_invalid_filter_values(self):
        self.client.force_login(self.member)

        response = self.client.get(
            reverse("api-project-task-list", args=[self.project.pk]),
            {"priority": "INVALID"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("details", response.json())

    def test_task_list_enforces_page_size_limit(self):
        self.client.force_login(self.member)

        response = self.client.get(
            reverse("api-project-task-list", args=[self.project.pk]),
            {"page_size": "101"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("page_size", response.json()["error"])

    def test_read_only_api_methods_return_json_405(self):
        self.client.force_login(self.member)

        response = self.client.post(reverse("api-project-list"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json(), {"error": "Method not allowed."})
        self.assertEqual(response["Allow"], "GET")

    def test_project_and_task_details_are_hidden_from_outsiders(self):
        self.client.force_login(self.outsider)

        project_response = self.client.get(
            reverse("api-project-detail", args=[self.project.pk])
        )
        task_response = self.client.get(
            reverse(
                "api-project-task-detail",
                args=[self.project.pk, self.task.pk],
            )
        )

        self.assertEqual(project_response.status_code, 404)
        self.assertEqual(task_response.status_code, 404)
