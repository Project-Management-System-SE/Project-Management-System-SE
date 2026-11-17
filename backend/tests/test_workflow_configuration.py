from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from projects.models import Project, ProjectMembership
from tasks.models import Task, WorkflowState, WorkflowTransition


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class WorkflowConfigurationTests(TestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", "owner", "Project Owner")
        self.member = self.create_user("member@example.com", "member", "Team Member")
        self.outsider = self.create_user("outsider@example.com", "outsider", "Outsider")
        self.project = Project.objects.create(name="Workflow project", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.owner,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )

    @staticmethod
    def create_user(email, username, full_name):
        return User.objects.create_user(
            email=email,
            username=username,
            full_name=full_name,
            password="safe-password-123",
        )

    def workflow_url(self):
        return reverse("tasks:workflow-configure", args=[self.project.pk])

    def board_url(self):
        return reverse("tasks:task-list", args=[self.project.pk])

    def workflow_payload(self, **overrides):
        payload = {
            "states": "Open\nIn Development\nQA\nReleased",
            "initial_state": "Open",
            "final_state": "Released",
            "transitions": (
                "Open -> In Development\n"
                "In Development -> QA\n"
                "QA -> Released\n"
                "In Development -> Open"
            ),
        }
        payload.update(overrides)
        return payload

    def test_project_manager_configures_states_and_transitions(self):
        self.client.force_login(self.owner)

        response = self.client.post(self.workflow_url(), self.workflow_payload())

        self.assertRedirects(
            response,
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.assertEqual(
            list(
                self.project.workflow_states.values_list("key", "name", "is_initial", "is_final")
            ),
            [
                ("OPEN", "Open", True, False),
                ("IN_DEVELOPMENT", "In Development", False, False),
                ("QA", "QA", False, False),
                ("RELEASED", "Released", False, True),
            ],
        )
        self.assertEqual(WorkflowTransition.objects.count(), 4)
        board = self.client.get(self.board_url())
        self.assertEqual(
            [column["value"] for column in board.context["board_columns"]],
            ["OPEN", "IN_DEVELOPMENT", "QA", "RELEASED"],
        )

    def test_custom_workflow_controls_task_creation_and_server_transitions(self):
        self.client.force_login(self.owner)
        self.client.post(self.workflow_url(), self.workflow_payload())
        task_create_url = reverse("tasks:task-create", args=[self.project.pk])

        create_response = self.client.post(
            task_create_url,
            {
                "title": "Custom workflow task",
                "description": "Exercise configured states.",
                "priority": Task.Priority.MEDIUM,
                "due_date": "",
                "assignee": self.member.pk,
                "status": "OPEN",
                "labels": "",
            },
        )

        self.assertEqual(create_response.status_code, 302)
        task = Task.objects.get(title="Custom workflow task")
        self.assertEqual(task.workflow_state.key, "OPEN")
        self.assertEqual(task.get_status_display(), "Open")
        self.assertEqual(task.status, Task.Status.TODO)

        status_url = reverse(
            "tasks:task-update-status",
            args=[self.project.pk, task.pk],
        )
        skipped_state_response = self.client.post(status_url, {"status": "QA"})
        self.assertEqual(skipped_state_response.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.workflow_state.key, "OPEN")

        for state_key in ("IN_DEVELOPMENT", "QA", "RELEASED"):
            response = self.client.post(status_url, {"status": state_key})
            self.assertEqual(response.status_code, 302)
            task.refresh_from_db()
            self.assertEqual(task.workflow_state.key, state_key)

        self.assertEqual(task.get_status_display(), "Released")
        self.assertEqual(task.status, Task.Status.DONE)
        self.assertIsNotNone(task.completed_at)

    def test_workflow_configuration_is_project_manager_only(self):
        self.client.force_login(self.member)

        response = self.client.post(self.workflow_url(), self.workflow_payload())

        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.project.workflow_states.exists())

        self.client.force_login(self.outsider)
        response = self.client.post(self.workflow_url(), self.workflow_payload())
        self.assertEqual(response.status_code, 404)

    def test_invalid_transitions_and_state_removal_with_tasks_are_rejected(self):
        self.client.force_login(self.owner)
        invalid_transition = self.workflow_payload(
            transitions="Open -> Missing State",
        )
        response = self.client.post(self.workflow_url(), invalid_transition)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.project.workflow_states.exists())

        task = Task.objects.create(
            project=self.project,
            title="Existing task",
            status=Task.Status.TODO,
            created_by=self.owner,
        )
        response = self.client.post(
            self.workflow_url(),
            self.workflow_payload(
                states="Open\nIn Development\nQA\nReleased",
            ),
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertIsNone(task.workflow_state_id)
        self.assertFalse(self.project.workflow_states.exists())
