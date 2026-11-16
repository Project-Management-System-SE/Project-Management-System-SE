from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from projects.models import Project, ProjectMembership
from tasks.models import Task


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TaskStatusViewTests(TestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", "owner", "Project Owner")
        self.assignee = self.create_user("assignee@example.com", "assignee", "Task Assignee")
        self.member = self.create_user("member@example.com", "member", "Team Member")
        self.outsider = self.create_user("outsider@example.com", "outsider", "Outsider")
        self.project = Project.objects.create(name="PMS", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.owner,
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
            created_by=self.owner,
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
        return reverse("tasks:task-list", args=[self.project.pk])

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

    def board_url(self):
        return f"{self.task_list_url()}?view=board"

    def test_project_member_can_view_task_fields_in_list(self):
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

    def test_assignee_can_update_status_and_it_persists(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.IN_PROGRESS},
        )

        self.assertRedirects(response, self.task_detail_url())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(self.task.completed_at, None)
        self.assertContains(self.client.get(self.task_detail_url()), "In Progress")
        self.assertContains(self.client.get(self.task_list_url()), "In Progress")

    def test_board_renders_status_controls_only_for_task_editors(self):
        self.client.force_login(self.assignee)

        response = self.client.get(self.board_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-task-status-form')
        self.assertContains(response, f'id="task-{self.task.pk}-status"')
        self.assertContains(response, "js/task_board.js")

        self.client.force_login(self.member)
        response = self.client.get(self.board_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-task-status-form')

    def test_board_status_ajax_update_returns_confirmation_and_persists(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.IN_PROGRESS},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "status": Task.Status.IN_PROGRESS,
                "status_display": "In Progress",
                "message": "Task status updated.",
            },
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertIsNone(self.task.completed_at)

    def test_board_status_ajax_rejects_invalid_status_without_persisting(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            self.status_url(),
            {"status": "NOT_A_WORKFLOW_STATUS"},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertIn("Select a valid choice", response.json()["error"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_board_status_ajax_rejects_unauthorized_project_and_task_access(self):
        self.client.force_login(self.member)

        task_response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
            HTTP_ACCEPT="application/json",
        )
        hidden_project_response = self.client.post(
            reverse(
                "tasks:task-update-status",
                args=[self.project.pk + 1000, self.task.pk],
            ),
            {"status": Task.Status.DONE},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(task_response.status_code, 403)
        self.assertFalse(task_response.json()["success"])
        self.assertEqual(hidden_project_response.status_code, 404)
        self.assertFalse(hidden_project_response.json()["success"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_board_status_ajax_requires_authentication(self):
        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])
        self.assertIn("session has expired", response.json()["error"])

        html_response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )
        self.assertEqual(html_response.status_code, 302)
        self.assertIn(reverse("login"), html_response.url)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_board_status_ajax_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.assignee)

        response = client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])
        self.assertIn("security token", response.json()["error"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_board_status_ajax_accepts_csrf_token_from_board(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.assignee)
        board_response = client.get(self.board_url())
        csrf_token = client.cookies["csrftoken"].value
        self.assertEqual(board_response.status_code, 200)

        response = client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
            HTTP_ACCEPT="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DONE)
        self.assertIsNotNone(self.task.completed_at)

    def test_project_manager_can_update_status(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )

        self.assertRedirects(response, self.task_detail_url())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DONE)
        self.assertIsNotNone(self.task.completed_at)

    def test_unassigned_member_cannot_update_status(self):
        self.client.force_login(self.member)

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )

        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_invalid_status_is_rejected_without_changing_task(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            self.status_url(),
            {"status": "NOT_A_WORKFLOW_STATUS"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Select a valid choice", status_code=400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_outsider_cannot_view_or_update_task(self):
        self.client.force_login(self.outsider)

        detail_response = self.client.get(self.task_detail_url())
        update_response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )

        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(update_response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_status_update_requires_post(self):
        self.client.force_login(self.assignee)

        response = self.client.get(self.status_url())

        self.assertEqual(response.status_code, 405)
        json_response = self.client.get(
            self.status_url(),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(json_response.status_code, 405)
        self.assertFalse(json_response.json()["success"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)
