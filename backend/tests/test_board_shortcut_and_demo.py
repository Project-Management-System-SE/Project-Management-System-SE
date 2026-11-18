from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from projects.models import Project, ProjectMembership, Sprint
from projects.reports import build_sprint_burndown, get_sprint_velocity_metrics

User = get_user_model()


def make_user(email, name):
    return User.objects.create_user(
        email=email, username=email.split("@")[0], full_name=name, password="StrongPass123!"
    )


class KanbanBoardShortcutTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com", "Owner")
        self.first = Project.objects.create(name="First", owner=self.owner, status=Project.Status.ACTIVE)
        self.second = Project.objects.create(name="Second", owner=self.owner, status=Project.Status.ACTIVE)
        for project in (self.first, self.second):
            ProjectMembership.objects.create(
                project=project, user=self.owner, project_role=ProjectMembership.Role.PROJECT_MANAGER
            )

    def board_url(self, project):
        return f"{reverse('tasks:task-list', args=[project.pk])}?view=board"

    def test_sidebar_shows_kanban_board_link(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("projects:dashboard"))
        self.assertContains(response, "Kanban board")
        self.assertContains(response, reverse("tasks:kanban-board"))

    def test_shortcut_opens_last_viewed_project_board(self):
        self.client.force_login(self.owner)
        self.client.get(reverse("tasks:task-list", args=[self.first.pk]))
        response = self.client.get(reverse("tasks:kanban-board"))
        self.assertRedirects(response, self.board_url(self.first))

    def test_shortcut_falls_back_to_an_active_project(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("tasks:kanban-board"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("?view=board", response["Location"])

    def test_user_without_projects_is_sent_to_project_list(self):
        outsider = make_user("outsider@example.com", "Outsider")
        self.client.force_login(outsider)
        response = self.client.get(reverse("tasks:kanban-board"))
        self.assertRedirects(response, reverse("projects:project-list"))

    def test_shortcut_ignores_a_project_the_user_cannot_see(self):
        outsider = make_user("outsider@example.com", "Outsider")
        session = self.client.session
        self.client.force_login(outsider)
        session = self.client.session
        session["last_board_project_id"] = self.first.pk
        session.save()
        response = self.client.get(reverse("tasks:kanban-board"))
        self.assertRedirects(response, reverse("projects:project-list"))

    def test_shortcut_requires_login(self):
        response = self.client.get(reverse("tasks:kanban-board"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])


class SeedDemoSprintsCommandTests(TestCase):
    def setUp(self):
        self.owner = make_user("pm@example.com", "Project Manager")
        self.member = make_user("dev@example.com", "Developer")

    def test_creates_completed_and_active_sprints_with_chart_data(self):
        out = StringIO()
        call_command("seed_demo_sprints", owner="pm@example.com", member=["dev@example.com"], stdout=out)
        project = Project.objects.get(name="Sprint Analytics Demo")

        self.assertEqual(project.sprints.filter(status=Sprint.Status.COMPLETED).count(), 2)
        active = project.sprints.get(status=Sprint.Status.ACTIVE)
        self.assertTrue(project.memberships.filter(user=self.member).exists())

        burndown = build_sprint_burndown(active)
        self.assertTrue(burndown["chart_available"])
        self.assertGreater(burndown["estimated_effort"], burndown["current_remaining_effort"])

        velocity = get_sprint_velocity_metrics(project)
        self.assertEqual(velocity["velocity_sprint_count"], 2)
        self.assertGreater(velocity["average_velocity"], 0)
        self.assertIn("3 sprints", out.getvalue())

    def test_refuses_to_run_twice_or_with_unknown_owner(self):
        call_command("seed_demo_sprints", owner="pm@example.com", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("seed_demo_sprints", owner="pm@example.com", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("seed_demo_sprints", owner="nobody@example.com", stdout=StringIO())
