from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from projects.models import Project, ProjectMembership
from tasks.models import Task


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaskViewTests(TestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", "owner", "Project Owner")
        self.manager = self.create_user("manager@example.com", "manager", "Project Manager")
        self.assignee = self.create_user("assignee@example.com", "assignee", "Task Assignee")
        self.member = self.create_user("member@example.com", "member", "Team Member")
        self.outsider = self.create_user("outsider@example.com", "outsider", "Outsider")
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="safe-password-123",
        )
        self.project = Project.objects.create(name="PMS", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.owner,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.manager,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.assignee,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.task = Task.objects.create(
            project=self.project,
            title="Prepare release",
            description="Complete release checks.",
            assignee=self.assignee,
            priority=Task.Priority.HIGH,
            due_date=date(2026, 11, 15),
        )

    @staticmethod
    def create_user(email, username, full_name):
        return User.objects.create_user(
            email=email,
            username=username,
            full_name=full_name,
            password="safe-password-123",
        )

    def task_list_url(self):
        return reverse("tasks:project-task-list", args=[self.project.pk])

    def task_detail_url(self):
        return reverse(
            "tasks:task-detail",
            args=[self.project.pk, self.task.pk],
        )

    def status_url(self):
        return reverse(
            "tasks:task-update-status",
            args=[self.project.pk, self.task.pk],
        )

    def test_project_member_can_view_task_list_and_task_fields(self):
        self.client.force_login(self.member)

        response = self.client.get(self.task_list_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prepare release")
        self.assertContains(response, "To Do")
        self.assertContains(response, "Task Assignee")
        self.assertContains(response, "High")
        self.assertContains(response, "Nov 15, 2026")

    def test_task_detail_shows_description_and_saved_fields(self):
        self.client.force_login(self.member)

        response = self.client.get(self.task_detail_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete release checks.")
        self.assertContains(response, "To Do")
        self.assertContains(response, "Task Assignee")
        self.assertContains(response, "High")
        self.assertContains(response, "Nov 15, 2026")
        self.assertNotContains(response, "Update status")

    def test_assigned_member_can_update_status_and_it_persists(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.IN_PROGRESS},
        )

        self.assertRedirects(response, self.task_detail_url())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        detail_response = self.client.get(self.task_detail_url())
        list_response = self.client.get(self.task_list_url())
        self.assertContains(detail_response, "In Progress")
        self.assertContains(list_response, "In Progress")

    def test_project_manager_can_update_any_task_status(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )

        self.assertRedirects(response, self.task_detail_url())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DONE)

    def test_admin_can_update_task_status(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )

        self.assertRedirects(response, self.task_detail_url())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DONE)

    def test_unassigned_member_cannot_update_task_status(self):
        self.client.force_login(self.member)

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )

        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TO_DO)

    def test_invalid_status_is_rejected_without_changing_task(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            self.status_url(),
            {"status": "NOT_A_WORKFLOW_STATUS"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Select a valid choice", status_code=400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TO_DO)

    def test_user_outside_project_cannot_view_or_update_task(self):
        self.client.force_login(self.outsider)

        detail_response = self.client.get(self.task_detail_url())
        update_response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )

        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(update_response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TO_DO)

    def test_task_list_only_includes_user_visible_projects(self):
        other_owner = self.create_user(
            "other-owner@example.com",
            "other-owner",
            "Other Owner",
        )
        other_project = Project.objects.create(name="Private Project", owner=other_owner)
        Task.objects.create(project=other_project, title="Private task")
        self.client.force_login(self.member)

        response = self.client.get(reverse("tasks:task-list"))

        self.assertContains(response, "Prepare release")
        self.assertNotContains(response, "Private task")

    def test_task_pages_require_login(self):
        response = self.client.get(self.task_list_url())

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.task_list_url()}",
        )

    def test_status_update_requires_post(self):
        self.client.force_login(self.assignee)

        response = self.client.get(self.status_url())

        self.assertEqual(response.status_code, 405)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TO_DO)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaskModelTests(TestCase):
    def test_task_defaults_to_to_do_and_medium_priority(self):
        owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="safe-password-123",
        )
        project = Project.objects.create(name="PMS", owner=owner)

        task = Task.objects.create(project=project, title="Review")

        self.assertEqual(task.status, Task.Status.TO_DO)
        self.assertEqual(task.priority, Task.Priority.MEDIUM)
        self.assertIsNone(task.assignee)
        self.assertIsNone(task.due_date)
