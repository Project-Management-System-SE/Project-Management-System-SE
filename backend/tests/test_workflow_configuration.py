from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from projects.models import (
    Project,
    ProjectMembership,
)
from projects.models import ProjectWorkflowTransition
from tasks.models import Task, WorkflowState, WorkflowTransition

User = get_user_model()


class ProjectWorkflowTransitionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="wf_cfg_owner",
            email="wf_cfg_owner@example.com",
            full_name="Config Owner",
            password="safe-password-123",
        )
        self.member = User.objects.create_user(
            username="wf_cfg_member",
            email="wf_cfg_member@example.com",
            full_name="Config Member",
            password="safe-password-123",
        )
        self.project = Project.objects.create(
            name="Workflow Integration Project",
            owner=self.owner,
            status=Project.Status.ACTIVE,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.task = Task.objects.create(
            title="Workflow Transition Test Task",
            project=self.project,
            created_by=self.owner,
            status=Task.Status.TODO,
        )

    def test_owner_can_access_workflow_settings(self):
        self.client.force_login(self.owner)
        url = reverse(
            "projects:project-workflow-settings",
            kwargs={"project_id": self.project.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_access_workflow_settings(self):
        self.client.force_login(self.member)
        url = reverse(
            "projects:project-workflow-settings",
            kwargs={"project_id": self.project.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_save_custom_workflow_rules_enforced(self):
        self.client.force_login(self.owner)
        url = reverse(
            "projects:project-workflow-settings",
            kwargs={"project_id": self.project.pk},
        )
        post_data = {
            "allow_todo_to_in_progress": "on",
            "allow_in_progress_to_in_review": "on",
            "allow_in_progress_to_todo": "on",
            "allow_in_review_to_done": "on",
            "allow_in_review_to_in_progress": "on",
            "allow_done_to_in_progress": "on",
            "allow_direct_todo_to_done": "on",
        }
        response = self.client.post(url, data=post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        status_url = reverse(
            "tasks:task-update-status",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )
        response = self.client.post(status_url, data={"status": Task.Status.DONE})
        self.task.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.task.status, Task.Status.DONE)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class WorkflowConfigurationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="safe-password-123",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Team Member",
            password="safe-password-123",
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com",
            username="outsider",
            full_name="Outsider",
            password="safe-password-123",
        )
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

    def workflow_url(self):
        return reverse("tasks:workflow-configure", args=[self.project.pk])

    def test_legacy_and_state_workflows_have_distinct_routes(self):
        self.assertEqual(
            reverse("projects:project-workflow-settings", args=[self.project.pk]),
            f"/projects/{self.project.pk}/workflow/",
        )
        self.assertEqual(
            self.workflow_url(),
            f"/projects/{self.project.pk}/workflow/configure/",
        )

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
