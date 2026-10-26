from datetime import date

from django.test import TestCase
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
        Project.objects.create(
            name="Active project",
            description="Active project description",
            owner=self.user,
            status=Project.Status.ACTIVE,
            due_date=date(2026, 11, 1),
        )
        Project.objects.create(name="Planned project", owner=self.user)

        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_projects"], 2)
        self.assertEqual(response.context["active_projects"], 1)
        self.assertIsNone(response.context["my_tasks"])
        self.assertIsNone(response.context["completed_tasks"])
        self.assertEqual(len(response.context["projects"]), 2)
        self.assertContains(response, 'href="/static/css/style.css"')
        self.assertContains(response, "Active project")
        self.assertContains(response, "Active project description")
        self.assertContains(response, "Active")
        self.assertContains(response, "Nov 1, 2026")
        self.assertContains(response, "Planned project")
        self.assertContains(response, "Progress unavailable")
        self.assertContains(response, "Task data unavailable")
        self.assertContains(response, 'href="/projects/new/"')

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
        self.assertContains(response, "Create Project")

    def test_project_list_renders_actual_description_and_status(self):
        Project.objects.create(
            name="Release planning",
            description="Prepare the upcoming release",
            owner=self.user,
            status=Project.Status.ON_HOLD,
        )

        response = self.client.get(reverse("projects:project-list"))

        self.assertContains(response, "Release planning")
        self.assertContains(response, "Prepare the upcoming release")
        self.assertContains(response, "On Hold")
        self.assertContains(response, "Progress unavailable")

    def test_project_form_supplies_template_fields(self):
        response = self.client.get(reverse("projects:project-create"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertEqual(
            list(response.context["project_status_choices"]),
            list(Project.Status.choices),
        )
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'href="/projects/"')
        self.assertContains(response, "Create Project")
        self.assertNotContains(response, ' disabled')
        for _, label in Project.Status.choices:
            self.assertContains(response, label)

    def test_admin_can_create_project_and_becomes_owner(self):
        admin_user = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="Project Admin",
            password="safe-password-123",
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("projects:project-create"),
            {
                "name": "New project",
                "description": "Created by a signed-in user",
                "status": Project.Status.ACTIVE,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse("projects:project-list"), 302)])
        self.assertContains(response, "Project created successfully.")
        self.assertContains(response, "New project")
        project = Project.objects.get()
        self.assertEqual(project.owner, admin_user)
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
        self.assertContains(response, "You must be signed in to create a project.")

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
        self.assertContains(response, 'aria-invalid="true"')
