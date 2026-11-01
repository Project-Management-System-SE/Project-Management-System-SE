from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from projects.models import Project, ProjectMembership, ProjectWorkflowTransition
from tasks.models import Task

User = get_user_model()


class WorkflowConfigurationIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="wf_cfg_owner",
            email="wf_cfg_owner@example.com",
            full_name="Config Owner",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="wf_cfg_member",
            email="wf_cfg_member@example.com",
            full_name="Config Member",
            password="password123",
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
        url = reverse("projects:project-workflow-settings", kwargs={"project_id": self.project.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_member_cannot_access_workflow_settings(self):
        self.client.force_login(self.member)
        url = reverse("projects:project-workflow-settings", kwargs={"project_id": self.project.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_save_custom_workflow_rules_enforced(self):
        self.client.force_login(self.owner)
        url = reverse("projects:project-workflow-settings", kwargs={"project_id": self.project.pk})
        post_data = {
            "allow_todo_to_in_progress": "on",
            "allow_in_progress_to_in_review": "on",
            "allow_in_progress_to_todo": "on",
            "allow_in_review_to_done": "on",
            "allow_in_review_to_in_progress": "on",
            "allow_done_to_in_progress": "on",
            "allow_direct_todo_to_done": "on",  # enabled fast track
        }
        resp = self.client.post(url, data=post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Now fast track TODO -> DONE transition should be allowed
        status_url = reverse(
            "tasks:task-update-status",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )
        resp2 = self.client.post(status_url, data={"status": "DONE"})
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DONE)
