import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from api.models import APIToken
from projects.models import Milestone, Project, ProjectMembership, Sprint
from tasks.models import Task, TaskComment, WorkflowState, WorkflowTransition


User = get_user_model()


class ApiSecurityPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="security_owner",
            email="security_owner@example.com",
            full_name="Security Owner",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="security_member",
            email="security_member@example.com",
            full_name="Security Member",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="security_outsider",
            email="security_outsider@example.com",
            full_name="Security Outsider",
            password="password123",
        )
        self.project = Project.objects.create(name="Private Project", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.owner,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        self.member_membership = ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.task = Task.objects.create(
            project=self.project,
            title="Owner task",
            created_by=self.owner,
        )
        self.sprint = Sprint.objects.create(
            project=self.project,
            name="Private sprint",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
        )
        self.milestone = Milestone.objects.create(
            project=self.project,
            name="Private milestone",
        )
        self.comment = TaskComment.objects.create(
            task=self.task,
            author=self.owner,
            content="Private comment",
        )
        self.other_project = Project.objects.create(
            name="Outsider Project",
            owner=self.outsider,
        )
        self.other_membership = ProjectMembership.objects.create(
            project=self.other_project,
            user=self.outsider,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        self.other_task = Task.objects.create(
            project=self.other_project,
            title="Outsider task",
            created_by=self.outsider,
        )
        self.other_comment = TaskComment.objects.create(
            task=self.other_task,
            author=self.outsider,
            content="Outsider comment",
        )
        self.owner_token = APIToken.objects.create(user=self.owner)
        self.member_token = APIToken.objects.create(user=self.member)
        self.outsider_token = APIToken.objects.create(user=self.outsider)

    def auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token.key}"}

    def test_cross_project_task_comment_membership_and_report_are_hidden(self):
        task_response = self.client.get(
            reverse("api:task-detail", kwargs={"task_id": self.other_task.pk}),
            **self.auth(self.member_token),
        )
        comment_response = self.client.get(
            reverse(
                "api:task-comments",
                kwargs={
                    "project_id": self.project.pk,
                    "task_id": self.other_task.pk,
                },
            ),
            **self.auth(self.member_token),
        )
        report_response = self.client.get(
            reverse(
                "api:project-reports",
                kwargs={"project_id": self.other_project.pk},
            ),
            **self.auth(self.member_token),
        )
        membership_response = self.client.patch(
            reverse(
                "api:project-member-detail",
                kwargs={
                    "project_id": self.project.pk,
                    "membership_id": self.other_membership.pk,
                },
            ),
            data=json.dumps({"role": ProjectMembership.Role.TEAM_MEMBER}),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(task_response.status_code, 404)
        self.assertEqual(comment_response.status_code, 404)
        self.assertEqual(report_response.status_code, 404)
        self.assertEqual(membership_response.status_code, 404)

    def test_team_member_cannot_manage_memberships_workflow_or_planning(self):
        membership_response = self.client.patch(
            reverse(
                "api:project-member-detail",
                kwargs={
                    "project_id": self.project.pk,
                    "membership_id": self.member_membership.pk,
                },
            ),
            data=json.dumps({"role": ProjectMembership.Role.PROJECT_MANAGER}),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        workflow_response = self.client.put(
            reverse(
                "api:project-workflow-update",
                kwargs={"project_id": self.project.pk},
            ),
            data=json.dumps({
                "states": ["Open", "Review", "Done"],
                "initial_state": "Open",
                "final_state": "Done",
                "transitions": [{"from": "Review", "to": "Done"}],
            }),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        sprint_response = self.client.post(
            reverse("api:project-sprints", kwargs={"project_id": self.project.pk}),
            data=json.dumps({
                "name": "Unauthorized sprint",
                "start_date": "2026-11-01",
                "end_date": "2026-11-14",
            }),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        milestone_response = self.client.post(
            reverse("api:project-milestones", kwargs={"project_id": self.project.pk}),
            data=json.dumps({"name": "Unauthorized milestone"}),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        self.assertEqual(membership_response.status_code, 403)
        self.assertEqual(workflow_response.status_code, 403)
        self.assertEqual(sprint_response.status_code, 403)
        self.assertEqual(milestone_response.status_code, 403)
        self.assertFalse(Sprint.objects.filter(name="Unauthorized sprint").exists())
        self.assertFalse(Milestone.objects.filter(name="Unauthorized milestone").exists())

    def test_team_member_cannot_delete_sprint_or_milestone(self):
        sprint_response = self.client.delete(
            reverse(
                "api:project-sprint-detail",
                kwargs={
                    "project_id": self.project.pk,
                    "sprint_id": self.sprint.pk,
                },
            ),
            **self.auth(self.member_token),
        )
        milestone_response = self.client.delete(
            reverse(
                "api:project-milestone-detail",
                kwargs={
                    "project_id": self.project.pk,
                    "milestone_id": self.milestone.pk,
                },
            ),
            **self.auth(self.member_token),
        )
        self.assertEqual(sprint_response.status_code, 403)
        self.assertEqual(milestone_response.status_code, 403)
        self.assertTrue(Sprint.objects.filter(pk=self.sprint.pk).exists())
        self.assertTrue(Milestone.objects.filter(pk=self.milestone.pk).exists())

    def test_project_member_can_change_unassigned_task_status(self):
        response = self.client.post(
            reverse("api:task-status", kwargs={"task_id": self.task.pk}),
            data=json.dumps({"status": Task.Status.IN_PROGRESS}),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)

    def test_outsider_cannot_change_task_status(self):
        response = self.client.post(
            reverse("api:task-status", kwargs={"task_id": self.task.pk}),
            data=json.dumps({"status": Task.Status.IN_PROGRESS}),
            content_type="application/json",
            **self.auth(self.outsider_token),
        )
        self.assertEqual(response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_custom_workflow_status_api_cannot_skip_review(self):
        open_state = WorkflowState.objects.create(
            project=self.project,
            key="OPEN",
            name="Open",
            position=0,
            is_initial=True,
        )
        review_state = WorkflowState.objects.create(
            project=self.project,
            key="QA",
            name="QA Review",
            position=1,
        )
        done_state = WorkflowState.objects.create(
            project=self.project,
            key="SHIPPED",
            name="Shipped",
            position=2,
            is_final=True,
        )
        WorkflowTransition.objects.create(from_state=open_state, to_state=review_state)
        WorkflowTransition.objects.create(from_state=review_state, to_state=done_state)

        self.task.delete()
        task = Task.objects.create(
            project=self.project,
            title="Custom workflow task",
            created_by=self.owner,
        )
        status_url = reverse("api:task-status", kwargs={"task_id": task.pk})
        direct_done = self.client.post(
            status_url,
            data=json.dumps({"status": "SHIPPED"}),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(direct_done.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.workflow_state.key, "OPEN")

        through_review = self.client.post(
            status_url,
            data=json.dumps({"status": "QA"}),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(through_review.status_code, 200)
        done = self.client.post(
            status_url,
            data=json.dumps({"status": "SHIPPED"}),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(done.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.workflow_state.key, "SHIPPED")
