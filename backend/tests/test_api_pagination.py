from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from api.models import APIToken
from projects.models import Project, ProjectMembership, Sprint
from tasks.models import Task


User = get_user_model()


class ApiPaginationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="pagination_owner",
            email="pagination_owner@example.com",
            full_name="Pagination Owner",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="pagination_member",
            email="pagination_member@example.com",
            full_name="Pagination Member",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="pagination_outsider",
            email="pagination_outsider@example.com",
            full_name="Pagination Outsider",
            password="password123",
        )
        self.project = Project.objects.create(
            name="Page Project",
            owner=self.owner,
            status=Project.Status.ACTIVE,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.sprint = Sprint.objects.create(
            project=self.project,
            name="Page Sprint",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
        )
        self.tasks = [
            Task.objects.create(
                project=self.project,
                title=f"Page task {index}",
                created_by=self.owner,
                sprint=self.sprint if index == 1 else None,
                status=Task.Status.TODO if index != 2 else Task.Status.IN_PROGRESS,
            )
            for index in range(1, 4)
        ]
        self.owner_token = APIToken.objects.create(user=self.owner)
        self.member_token = APIToken.objects.create(user=self.member)
        self.outsider_token = APIToken.objects.create(user=self.outsider)

    def auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token.key}"}

    def test_task_list_pagination_boundaries(self):
        url = reverse("api:project-tasks", kwargs={"project_id": self.project.pk})
        first = self.client.get(
            url,
            {"page": 1, "page_size": 2},
            **self.auth(self.member_token),
        )
        second = self.client.get(
            url,
            {"page": 2, "page_size": 2},
            **self.auth(self.member_token),
        )
        beyond = self.client.get(
            url,
            {"page": 3, "page_size": 2},
            **self.auth(self.member_token),
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["count"], 3)
        self.assertEqual(len(first.json()["data"]["tasks"]), 2)
        self.assertEqual(first.json()["data"]["next_page"], 2)
        self.assertEqual(second.json()["data"]["previous_page"], 1)
        self.assertEqual(len(second.json()["data"]["tasks"]), 1)
        self.assertEqual(beyond.status_code, 400)

    def test_task_filters_combine_and_remain_project_scoped(self):
        url = reverse("api:project-tasks", kwargs={"project_id": self.project.pk})
        response = self.client.get(
            url,
            {"status": Task.Status.TODO, "sprint": self.sprint.pk, "page_size": 1},
            **self.auth(self.member_token),
        )
        self.assertEqual(response.status_code, 200)
        results = response.json()["data"]["tasks"]
        self.assertEqual([task["title"] for task in results], ["Page task 1"])

        invalid_sprint = self.client.get(
            url,
            {"sprint": self.project.pk + 100},
            **self.auth(self.member_token),
        )
        self.assertEqual(invalid_sprint.status_code, 400)

        outsider = self.client.get(
            url,
            {"status": Task.Status.TODO},
            **self.auth(self.outsider_token),
        )
        self.assertEqual(outsider.status_code, 404)

    def test_list_query_parameters_are_validated(self):
        url = reverse("api:project-tasks", kwargs={"project_id": self.project.pk})
        bad_date = self.client.get(
            url,
            {"due_after": "not-a-date"},
            **self.auth(self.owner_token),
        )
        repeated_page = self.client.get(
            f"{url}?page=1&page=2",
            **self.auth(self.owner_token),
        )
        invalid_size = self.client.get(
            url,
            {"page_size": "101"},
            **self.auth(self.owner_token),
        )
        self.assertEqual(bad_date.status_code, 400)
        self.assertEqual(repeated_page.status_code, 400)
        self.assertEqual(invalid_size.status_code, 400)

    def test_project_list_is_paginated_and_filterable(self):
        Project.objects.create(
            name="Planned Project",
            owner=self.owner,
            status=Project.Status.PLANNED,
        )
        url = reverse("api:project-list")
        response = self.client.get(
            url,
            {"status": Project.Status.PLANNED, "page_size": 1},
            **self.auth(self.owner_token),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["count"], 1)
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(data["projects"][0]["status"], Project.Status.PLANNED)
