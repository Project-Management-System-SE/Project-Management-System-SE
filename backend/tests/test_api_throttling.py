import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from api.models import APIToken
from projects.models import Project
from tasks.models import Task


@override_settings(
    API_RATE_LIMIT_READ=2,
    API_RATE_LIMIT_WRITE=1,
    API_RATE_LIMIT_WINDOW_SECONDS=60,
)
class ApiThrottlingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="throttle_user",
            email="throttle@example.com",
            full_name="Throttle User",
            password="password123",
        )
        self.project = Project.objects.create(name="Throttle project", owner=self.user)
        self.task = Task.objects.create(
            project=self.project,
            title="Throttle task",
            created_by=self.user,
            status=Task.Status.TODO,
        )
        self.token = APIToken.objects.create(user=self.user)
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token.key}"}

    def tearDown(self):
        cache.clear()

    def test_read_budget_is_per_authenticated_user_for_token_and_session(self):
        url = reverse("api:project-list")
        first = self.client.get(url, **self.auth_headers)
        self.client.force_login(self.user)
        second = self.client.get(url)
        third = self.client.get(url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third["Retry-After"], "60")
        self.assertEqual(third.json()["status"], "error")

    def test_write_budget_throttles_and_keeps_first_write(self):
        url = reverse("api:task-status", kwargs={"task_id": self.task.pk})
        payload = json.dumps({"status": Task.Status.IN_PROGRESS})
        first = self.client.post(
            url,
            data=payload,
            content_type="application/json",
            **self.auth_headers,
        )
        second = self.client.post(
            url,
            data=payload,
            content_type="application/json",
            **self.auth_headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)

    def test_session_api_routes_share_the_configured_rate_limit(self):
        self.client.force_login(self.user)
        url = reverse("api-project-list")
        first = self.client.get(url)
        second = self.client.get(url)
        third = self.client.get(url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third["Retry-After"], "60")
