import json
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from api.models import APIToken
from projects.models import Project, ProjectMembership
from tasks.models import Task

User = get_user_model()


class RestApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="api_user",
            email="api@example.com",
            full_name="API User",
            password="password123",
        )
        self.token = APIToken.objects.create(user=self.user, name="Test Token")
        self.project = Project.objects.create(
            name="API Test Project",
            owner=self.user,
            status=Project.Status.ACTIVE,
        )
        self.task = Task.objects.create(
            title="Initial API Task",
            project=self.project,
            created_by=self.user,
            status=Task.Status.TODO,
        )
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token.key}"}

    def test_unauthenticated_request_rejected(self):
        resp = self.client.get(reverse("api:project-list"))
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_project_list(self):
        resp = self.client.get(reverse("api:project-list"), **self.auth_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["projects"][0]["name"], "API Test Project")

    def test_task_creation_via_api(self):
        url = reverse("api:project-tasks", kwargs={"project_id": self.project.pk})
        post_data = {
            "title": "Created via API",
            "priority": "HIGH",
            "description": "API description",
        }
        resp = self.client.post(
            url,
            data=json.dumps(post_data),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["data"]["title"], "Created via API")

    def test_session_authentication_cannot_bypass_csrf_on_token_api_writes(self):
        self.client.force_login(self.user)
        url = reverse("api:project-tasks", kwargs={"project_id": self.project.pk})

        response = self.client.post(
            url,
            data=json.dumps({"title": "Session-authenticated write"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Task.objects.filter(title="Session-authenticated write").exists())

    def test_task_status_transition_enforced(self):
        status_url = reverse("api:task-status", kwargs={"task_id": self.task.pk})
        # Invalid jump from TODO -> DONE
        resp = self.client.post(
            status_url,
            data=json.dumps({"status": "DONE"}),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(resp.status_code, 400)

        # Valid jump TODO -> IN_PROGRESS
        resp2 = self.client.post(
            status_url,
            data=json.dumps({"status": "IN_PROGRESS"}),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(resp2.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)

    def test_openapi_spec_accessible(self):
        resp = self.client.get(reverse("api:openapi-spec"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("openapi", resp.json())

    def test_api_docs_viewer_and_expanded_paths(self):
        resp = self.client.get(reverse("api:api-docs"))
        self.assertEqual(resp.status_code, 200)
        spec = self.client.get(reverse("api:openapi-spec")).json()
        self.assertIn("/api/v1/projects/{project_id}/members/", spec["paths"])
        self.assertIn("/api/v1/projects/{project_id}/reports/", spec["paths"])

    def test_authentication_and_method_errors_share_the_api_error_envelope(self):
        unauthenticated = self.client.get(reverse("api:project-list"))
        invalid_token = self.client.get(
            reverse("api:project-list"),
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )
        wrong_method = self.client.post(
            reverse("api:project-list"),
            **self.auth_headers,
        )

        for response, expected_status in (
            (unauthenticated, 401),
            (invalid_token, 401),
            (wrong_method, 405),
        ):
            self.assertEqual(response.status_code, expected_status)
            self.assertEqual(set(response.json()), {"status", "message", "errors"})
            self.assertEqual(response.json()["status"], "error")
        self.assertEqual(wrong_method["Allow"], "GET")

    def test_invalid_payloads_use_consistent_json_errors(self):
        url = reverse("api:project-tasks", kwargs={"project_id": self.project.pk})
        malformed = self.client.post(
            url,
            data="{",
            content_type="application/json",
            **self.auth_headers,
        )
        non_object = self.client.post(
            url,
            data=json.dumps(["not", "an", "object"]),
            content_type="application/json",
            **self.auth_headers,
        )
        unsupported_type = self.client.post(
            url,
            data="title=Task",
            content_type="application/x-www-form-urlencoded",
            **self.auth_headers,
        )

        for response, status_code in (
            (malformed, 400),
            (non_object, 400),
            (unsupported_type, 415),
        ):
            self.assertEqual(response.status_code, status_code)
            self.assertEqual(set(response.json()), {"status", "message", "errors"})
            self.assertEqual(response.json()["status"], "error")

    def test_token_writes_work_with_csrf_checks_but_session_writes_stay_blocked(self):
        csrf_checked = Client(enforce_csrf_checks=True)
        url = reverse("api:project-members", kwargs={"project_id": self.project.pk})
        new_user = User.objects.create_user(
            username="csrf_api_member",
            email="csrf_api_member@example.com",
            full_name="CSRF API Member",
            password="password123",
        )
        token_response = csrf_checked.post(
            url,
            data=json.dumps(
                {"user_id": new_user.pk, "role": ProjectMembership.Role.TEAM_MEMBER}
            ),
            content_type="application/json",
            **self.auth_headers,
        )
        self.assertEqual(token_response.status_code, 201)

        csrf_checked.force_login(self.user)
        session_response = csrf_checked.post(
            url,
            data=json.dumps(
                {"user_id": new_user.pk, "role": ProjectMembership.Role.TEAM_MEMBER}
            ),
            content_type="application/json",
        )
        self.assertEqual(session_response.status_code, 403)
        self.assertEqual(session_response.json()["status"], "error")
