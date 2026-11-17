import csv
import io
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from projects.models import Project, ProjectMembership, Sprint
from tasks.models import Task


class ProjectReportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="test-pass-123",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Team Member",
            password="test-pass-123",
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com",
            username="outsider",
            full_name="Outsider",
            password="test-pass-123",
        )
        self.project = Project.objects.create(name="Report project", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.done_task = Task.objects.create(
            project=self.project,
            title="Completed",
            created_by=self.owner,
            assignee=self.member,
            status=Task.Status.DONE,
            estimated_effort=Decimal("3.00"),
            actual_effort=Decimal("4.00"),
        )
        Task.objects.create(
            project=self.project,
            title="Open",
            created_by=self.owner,
            assignee=self.member,
            estimated_effort=Decimal("5.00"),
        )
        self.client.force_login(self.member)

    def read_report(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))

    def test_progress_report_summarizes_project_metrics(self):
        response = self.client.get(
            reverse("projects:project-progress-report", args=[self.project.pk])
        )

        rows = self.read_report(response)

        self.assertEqual(rows[1][3:6], ["2", "1", "50.0"])
        self.assertEqual(rows[1][6:], ["8", "4"])
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_progress_report_escapes_spreadsheet_formulas(self):
        self.project.name = "=1+1"
        self.project.save()

        response = self.client.get(
            reverse("projects:project-progress-report", args=[self.project.pk])
        )

        rows = self.read_report(response)

        self.assertEqual(rows[1][1], "'=1+1")

    def test_reports_require_project_visibility(self):
        self.client.force_login(self.outsider)

        response = self.client.get(
            reverse("projects:project-progress-report", args=[self.project.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_velocity_report_uses_completed_tasks_in_closed_sprints(self):
        sprint = Sprint.objects.create(
            project=self.project,
            name="Sprint 1",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
            status=Sprint.Status.COMPLETED,
        )
        self.done_task.sprint = sprint
        self.done_task.save()

        response = self.client.get(
            reverse("projects:project-velocity-report", args=[self.project.pk])
        )

        rows = self.read_report(response)

        self.assertEqual(rows[1][1], "Sprint 1")
        self.assertEqual(rows[1][4:], ["1", "3", "4"])

    def test_workload_report_groups_tasks_by_member(self):
        response = self.client.get(
            reverse("projects:project-workload-report", args=[self.project.pk])
        )

        rows = self.read_report(response)

        self.assertEqual(rows[1][2], self.member.email)
        self.assertEqual(rows[1][3:], ["2", "1", "8", "4"])
