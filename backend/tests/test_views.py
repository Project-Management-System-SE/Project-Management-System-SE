from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from projects.models import Project

TEST_TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [Path(__file__).resolve().parent / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {},
    }
]


@override_settings(TEMPLATES=TEST_TEMPLATES)
class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="safe-password-123",
        )

    def test_dashboard_supplies_template_context(self):
        Project.objects.create(name="Active project", owner=self.user, status=Project.Status.ACTIVE)
        Project.objects.create(name="Planned project", owner=self.user)

        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_projects"], 2)
        self.assertEqual(response.context["active_projects"], 1)
        self.assertIsNone(response.context["my_tasks"])
        self.assertIsNone(response.context["completed_tasks"])
        self.assertEqual(len(response.context["projects"]), 2)

    def test_dashboard_alias_renders(self):
        response = self.client.get(reverse("projects:dashboard-alias"))

        self.assertEqual(response.status_code, 200)


@override_settings(TEMPLATES=TEST_TEMPLATES)
class ProjectViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="safe-password-123",
        )

    def test_project_list_supplies_projects(self):
        Project.objects.create(name="PMS", owner=self.user)

        response = self.client.get(reverse("projects:project-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["projects"]), [Project.objects.get()])

    def test_project_form_supplies_template_fields(self):
        response = self.client.get(reverse("projects:project-create"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertEqual(
            list(response.context["project_status_choices"]),
            list(Project.Status.choices),
        )

    def test_authenticated_user_can_create_project(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("projects:project-create"),
            {
                "name": "New project",
                "description": "Created by a signed-in user",
                "status": Project.Status.ACTIVE,
            },
        )

        self.assertRedirects(response, reverse("projects:project-list"))
        project = Project.objects.get()
        self.assertEqual(project.owner, self.user)
        self.assertEqual(project.status, Project.Status.ACTIVE)

    def test_anonymous_user_cannot_create_project(self):
        response = self.client.post(
            reverse("projects:project-create"),
            {
                "name": "Anonymous project",
                "description": "",
                "status": Project.Status.PLANNED,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.exists())
        self.assertTrue(response.context["form"].non_field_errors())

    def test_invalid_project_data_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("projects:project-create"),
            {
                "name": "",
                "description": "",
                "status": Project.Status.PLANNED,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.exists())
        self.assertIn("name", response.context["form"].errors)
