from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from projects.models import Project, ProjectMembership
from tasks.models import Task

User = get_user_model()


class ReportSecurityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="rep_sec_owner",
            email="owner_sec@example.com",
            full_name="Report Owner",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="rep_sec_member",
            email="member_sec@example.com",
            full_name="Report Member",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="rep_sec_outsider",
            email="outsider_sec@example.com",
            full_name="Report Outsider",
            password="password123",
        )
        self.project = Project.objects.create(
            name="Confidential Project",
            owner=self.owner,
            status=Project.Status.ACTIVE,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.task = Task.objects.create(
            title="Secret Task",
            project=self.project,
            created_by=self.owner,
            status=Task.Status.TODO,
        )

    def test_anonymous_user_redirected_to_login(self):
        url = reverse("projects:project-reports", kwargs={"project_id": self.project.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_member_can_view_reports(self):
        self.client.force_login(self.member)
        url = reverse("projects:project-reports", kwargs={"project_id": self.project.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_outsider_cannot_view_reports(self):
        self.client.force_login(self.outsider)
        url = reverse("projects:project-reports", kwargs={"project_id": self.project.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_member_can_download_csv(self):
        self.client.force_login(self.member)
        url = reverse("projects:project-report-download", kwargs={"project_id": self.project.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("Secret Task", resp.content.decode())

    def test_outsider_cannot_download_csv(self):
        self.client.force_login(self.outsider)
        url = reverse("projects:project-report-download", kwargs={"project_id": self.project.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
