from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Project, Sprint
from projects.reports import (
    generate_summary_report_csv,
    generate_tasks_report_csv,
    get_project_progress_metrics,
    get_sprint_velocity_metrics,
    get_team_workload_metrics,
)
from tasks.models import Task

User = get_user_model()


class ReportMetricsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="rep_user",
            email="rep_user@example.com",
            full_name="Report User",
            password="password123",
        )
        self.project = Project.objects.create(
            name="Report Metrics Project",
            owner=self.user,
            status=Project.Status.ACTIVE,
        )

    def test_empty_project_metrics(self):
        metrics = get_project_progress_metrics(self.project)
        self.assertEqual(metrics["total_tasks"], 0)
        self.assertEqual(metrics["completion_rate"], 0.0)
        self.assertEqual(metrics["total_estimated"], Decimal("0.00"))
        self.assertEqual(metrics["total_actual"], Decimal("0.00"))

    def test_project_progress_calculation(self):
        Task.objects.create(
            title="Task 1",
            project=self.project,
            created_by=self.user,
            status=Task.Status.DONE,
            estimated_effort=Decimal("5.00"),
            actual_effort=Decimal("4.50"),
        )
        Task.objects.create(
            title="Task 2",
            project=self.project,
            created_by=self.user,
            status=Task.Status.IN_PROGRESS,
            estimated_effort=Decimal("3.00"),
            actual_effort=Decimal("1.00"),
        )
        metrics = get_project_progress_metrics(self.project)
        self.assertEqual(metrics["total_tasks"], 2)
        self.assertEqual(metrics["completed_tasks"], 1)
        self.assertEqual(metrics["completion_rate"], 50.0)
        self.assertEqual(metrics["total_estimated"], Decimal("8.00"))
        self.assertEqual(metrics["total_actual"], Decimal("5.50"))
        self.assertEqual(metrics["effort_variance"], Decimal("-2.50"))

    def test_sprint_velocity_calculation(self):
        sprint = Sprint.objects.create(
            project=self.project,
            name="Sprint 1",
            status=Sprint.Status.COMPLETED,
        )
        Task.objects.create(
            title="Sprint Task",
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            status=Task.Status.DONE,
            actual_effort=Decimal("10.00"),
        )
        velocity = get_sprint_velocity_metrics(self.project)
        self.assertEqual(velocity["closed_sprint_count"], 1)
        self.assertEqual(velocity["average_velocity"], Decimal("10.00"))

    def test_csv_generation_not_empty(self):
        Task.objects.create(
            title="CSV Task",
            project=self.project,
            created_by=self.user,
            status=Task.Status.TODO,
        )
        tasks_csv = generate_tasks_report_csv(self.project)
        self.assertIn("Task ID,Project,Title", tasks_csv)
        self.assertIn("CSV Task", tasks_csv)

        summary_csv = generate_summary_report_csv(self.project)
        self.assertIn("PROJECT SUMMARY REPORT", summary_csv)
        self.assertIn("Report Metrics Project", summary_csv)
