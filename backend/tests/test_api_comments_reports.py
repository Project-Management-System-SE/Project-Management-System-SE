import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from api.models import APIToken
from projects.models import Project, ProjectMembership
from tasks.models import Task, TaskComment


User = get_user_model()


class CommentsAndReportsApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="report_owner",
            email="report_owner@example.com",
            full_name="Report Owner",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="report_member",
            email="report_member@example.com",
            full_name="Report Member",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="report_outsider",
            email="report_outsider@example.com",
            full_name="Report Outsider",
            password="password123",
        )
        self.project = Project.objects.create(
            name="Comments and Reports API",
            owner=self.owner,
            status=Project.Status.ACTIVE,
        )
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
        self.task = Task.objects.create(
            title="Reported API Task",
            project=self.project,
            created_by=self.owner,
            status=Task.Status.TODO,
        )
        self.owner_token = APIToken.objects.create(user=self.owner)
        self.member_token = APIToken.objects.create(user=self.member)
        self.outsider_token = APIToken.objects.create(user=self.outsider)
        self.comments_url = reverse(
            "api:task-comments",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )

    def auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token.key}"}

    def test_comment_create_list_update_delete(self):
        create_response = self.client.post(
            self.comments_url,
            data=json.dumps({"content": "Created through API"}),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        self.assertEqual(create_response.status_code, 201)
        comment = TaskComment.objects.get(content="Created through API")

        list_response = self.client.get(
            self.comments_url,
            **self.auth(self.member_token),
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["data"]["count"], 1)

        detail_url = reverse(
            "api:task-comment-detail",
            kwargs={
                "project_id": self.project.pk,
                "task_id": self.task.pk,
                "comment_id": comment.pk,
            },
        )
        patch_response = self.client.patch(
            detail_url,
            data=json.dumps({"content": "Updated through API"}),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        self.assertEqual(patch_response.status_code, 200)

        delete_response = self.client.delete(
            detail_url,
            **self.auth(self.member_token),
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(TaskComment.objects.filter(pk=comment.pk).exists())

    def test_comment_payload_and_cross_project_access_are_validated(self):
        invalid_response = self.client.post(
            self.comments_url,
            data=json.dumps({"content": ""}),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        self.assertEqual(invalid_response.status_code, 400)

        outsider_response = self.client.get(
            self.comments_url,
            **self.auth(self.outsider_token),
        )
        self.assertEqual(outsider_response.status_code, 404)

    def test_authorization_prevents_other_user_comment_update(self):
        comment = TaskComment.objects.create(
            task=self.task,
            author=self.owner,
            content="Owner comment",
        )
        detail_url = reverse(
            "api:task-comment-detail",
            kwargs={
                "project_id": self.project.pk,
                "task_id": self.task.pk,
                "comment_id": comment.pk,
            },
        )
        response = self.client.patch(
            detail_url,
            data=json.dumps({"content": "Unauthorized edit"}),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_project_report_returns_real_structured_metrics(self):
        url = reverse(
            "api:project-reports",
            kwargs={"project_id": self.project.pk},
        )
        response = self.client.get(url, **self.auth(self.member_token))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["project_id"], self.project.pk)
        self.assertIn("progress", data)
        self.assertIn("velocity", data)
        self.assertIn("workload", data)
        self.assertEqual(data["progress"]["total_tasks"], 1)

        outsider_response = self.client.get(
            url,
            **self.auth(self.outsider_token),
        )
        self.assertEqual(outsider_response.status_code, 404)
