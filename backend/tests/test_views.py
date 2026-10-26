from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from projects.models import Project


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
        self.assertContains(response, "Active project")
        self.assertContains(response, "Planned project")
        self.assertContains(response, "Progress unavailable")
        self.assertContains(response, "—")

    def test_dashboard_renders_empty_state(self):
        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No projects to show yet")
        self.assertContains(response, "Create your first project")

    def test_dashboard_limits_recent_projects_to_five(self):
        for index in range(6):
            Project.objects.create(
                name=f"Project {index}",
                owner=self.user,
            )

        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["projects"]), 5)

    def test_dashboard_alias_renders(self):
        response = self.client.get(reverse("projects:dashboard-alias"))

        self.assertEqual(response.status_code, 200)


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
        self.assertContains(response, "PMS")

    def test_project_list_renders_empty_state(self):
        response = self.client.get(reverse("projects:project-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No projects yet")
        self.assertContains(response, "Create your first project")

    def test_project_list_renders_project_fields(self):
        Project.objects.create(
            name="Release planning",
            description="Plan the release",
            owner=self.user,
            status=Project.Status.ON_HOLD,
        )

        response = self.client.get(reverse("projects:project-list"))

        self.assertContains(response, "Release planning")
        self.assertContains(response, "ON_HOLD")
        self.assertContains(response, "Progress unavailable")
        project = response.context["projects"][0]
        self.assertEqual(project.description, "Plan the release")

    def test_project_form_supplies_template_fields(self):
        response = self.client.get(reverse("projects:project-create"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertEqual(
            list(response.context["project_status_choices"]),
            list(Project.Status.choices),
        )
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        for _, label in Project.Status.choices:
            self.assertContains(response, label)

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

    def test_project_creation_with_default_status_sets_owner(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("projects:project-create"),
            {
                "name": "Default status project",
                "description": "",
                "status": Project.Status.PLANNED,
            },
        )

        self.assertRedirects(response, reverse("projects:project-list"))
        project = Project.objects.get(name="Default status project")
        self.assertEqual(project.owner, self.user)
        self.assertEqual(project.status, Project.Status.PLANNED)

    def test_project_creation_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        client.get(reverse("projects:project-create"))
        post_data = {
            "name": "CSRF protected project",
            "description": "",
            "status": Project.Status.PLANNED,
        }
        missing_token_response = client.post(
            reverse("projects:project-create"),
            post_data,
        )

        self.assertEqual(missing_token_response.status_code, 403)
        self.assertFalse(Project.objects.exists())

        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("projects:project-create"),
            post_data,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertRedirects(response, reverse("projects:project-list"))
        self.assertTrue(Project.objects.filter(owner=self.user).exists())

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
        self.assertContains(response, "This field is required.")

    def test_invalid_status_is_rejected_by_project_view(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("projects:project-create"),
            {
                "name": "Invalid status project",
                "description": "",
                "status": "UNKNOWN",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.exists())
        self.assertIn("status", response.context["form"].errors)
