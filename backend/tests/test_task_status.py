from datetime import date

from django.test import TestCase, override_settings
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

    def test_project_member_can_view_task_fields_in_list(self):
        self.client.force_login(self.member)

        response = self.client.get(self.task_list_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [column["value"] for column in response.context["board_columns"]],
            [
                Task.Status.BACKLOG,
                Task.Status.TODO,
                Task.Status.IN_PROGRESS,
                Task.Status.REVIEW,
                Task.Status.DONE,
            ],
        )
        self.assertContains(response, "Prepare release")
        self.assertContains(response, "To Do")
        self.assertContains(response, "Task Assignee")
        self.assertContains(response, "High")
        self.assertContains(response, "Nov 15, 2026")
        self.assertContains(response, "No tasks in this stage.")
        self.assertNotContains(response, 'class="kanban-move-form"')

    def test_board_groups_project_tasks_in_status_columns(self):
        created_tasks = {
            status: Task.objects.create(
                project=self.project,
                title=f"Task in {status}",
                status=status,
                created_by=self.owner,
            )
            for status, _ in Task.Status.choices
        }
        unrelated_project = Project.objects.create(
            name="Unrelated project",
            owner=self.owner,
        )
        Task.objects.create(
            project=unrelated_project,
            title="Must not appear on this board",
            created_by=self.owner,
        )
        self.client.force_login(self.owner)

        response = self.client.get(self.task_list_url())

        self.assertEqual(response.status_code, 200)
        columns = {
            column["value"]: column["tasks"]
            for column in response.context["board_columns"]
        }
        for status, task in created_tasks.items():
            self.assertIn(task, columns[status])
        self.assertNotContains(response, "Must not appear on this board")
        self.assertContains(response, "Task Assignee")
        self.assertContains(response, "High")
        self.assertContains(response, "Nov 15, 2026")

    def test_authorized_task_assignee_can_move_task_from_board(self):
        self.client.force_login(self.assignee)

        response = self.client.get(self.task_list_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'draggable="true"')
        self.assertContains(response, 'name="status"')
        self.assertContains(response, 'value="IN_PROGRESS"')

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

    def test_task_must_follow_workflow_and_pass_review_before_done(self):
        self.client.force_login(self.owner)

        skipped_review_response = self.client.post(
            self.status_url(),
            {"status": Task.Status.DONE},
        )
        self.assertEqual(skipped_review_response.status_code, 400)
        self.assertContains(
            skipped_review_response,
            "Tasks must pass through Review before they can be marked Done.",
            status_code=400,
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

        for status in [
            Task.Status.IN_PROGRESS,
            Task.Status.REVIEW,
            Task.Status.DONE,
        ]:
            response = self.client.post(self.status_url(), {"status": status})
            self.assertRedirects(response, self.task_detail_url())
            self.task.refresh_from_db()
            self.assertEqual(self.task.status, status)

        self.assertIsNotNone(self.task.completed_at)
        self.assertContains(self.client.get(self.task_list_url()), "Review")

    def test_status_can_move_back_one_stage_but_done_only_returns_to_review(self):
        self.client.force_login(self.owner)
        self.task.status = Task.Status.REVIEW
        self.task.save()

        response = self.client.post(
            self.status_url(),
            {"status": Task.Status.IN_PROGRESS},
        )

        self.assertRedirects(response, self.task_detail_url())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertIsNone(self.task.completed_at)

        self.task.status = Task.Status.DONE
        self.task.save()
        invalid_reverse_response = self.client.post(
            self.status_url(),
            {"status": Task.Status.IN_PROGRESS},
        )
        self.assertEqual(invalid_reverse_response.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DONE)

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
        self.assertContains(
            response,
            "This status change is not allowed by the default workflow.",
            status_code=400,
        )
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
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_board_status_form_only_offers_allowed_next_stages(self):
        self.client.force_login(self.assignee)

        response = self.client.get(self.task_detail_url())

        self.assertEqual(response.status_code, 200)
        choices = list(response.context["status_form"].fields["status"].choices)
        self.assertEqual(
            choices,
            [
                (Task.Status.BACKLOG, "Backlog"),
                (Task.Status.TODO, "To Do"),
                (Task.Status.IN_PROGRESS, "In Progress"),
            ],
        )
