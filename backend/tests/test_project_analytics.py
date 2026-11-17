from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from projects.analytics import build_sprint_burndown, completed_sprint_metrics
from projects.models import Project, Sprint
from tasks.models import Task


class SprintAnalyticsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="test-pass-123",
        )
        self.project = Project.objects.create(name="Analytics", owner=self.owner)
        self.sprint = Sprint.objects.create(
            project=self.project,
            name="Sprint 1",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 10),
            status=Sprint.Status.ACTIVE,
        )

    def test_burndown_uses_task_completion_dates_and_caps_chart_points(self):
        completed_early = Task.objects.create(
            project=self.project,
            sprint=self.sprint,
            title="Completed early",
            created_by=self.owner,
            status=Task.Status.DONE,
            estimated_effort=Decimal("2.00"),
        )
        completed_late = Task.objects.create(
            project=self.project,
            sprint=self.sprint,
            title="Completed late",
            created_by=self.owner,
            status=Task.Status.DONE,
            estimated_effort=Decimal("3.00"),
        )
        Task.objects.create(
            project=self.project,
            sprint=self.sprint,
            title="Remaining",
            created_by=self.owner,
            estimated_effort=Decimal("5.00"),
        )
        Task.objects.filter(pk=completed_early.pk).update(
            completed_at=datetime(2026, 11, 2, tzinfo=datetime_timezone.utc)
        )
        Task.objects.filter(pk=completed_late.pk).update(
            completed_at=datetime(2026, 11, 4, tzinfo=datetime_timezone.utc)
        )

        chart = build_sprint_burndown(self.sprint, today=date(2026, 11, 5))

        self.assertEqual(chart["total_effort"], Decimal("10.00"))
        self.assertEqual(chart["current_remaining_effort"], Decimal("5.00"))
        self.assertTrue(chart["has_estimates"])
        self.assertLessEqual(len(chart["actual_points"].split()), 61)

    def test_completed_sprint_velocity_counts_only_completed_effort(self):
        self.sprint.status = Sprint.Status.COMPLETED
        self.sprint.save()
        Task.objects.create(
            project=self.project,
            sprint=self.sprint,
            title="Completed",
            created_by=self.owner,
            status=Task.Status.DONE,
            estimated_effort=Decimal("8.00"),
            actual_effort=Decimal("9.00"),
        )
        Task.objects.create(
            project=self.project,
            sprint=self.sprint,
            title="Not completed",
            created_by=self.owner,
            estimated_effort=Decimal("5.00"),
            actual_effort=Decimal("2.00"),
        )

        sprint_metrics = completed_sprint_metrics(self.project).get()

        self.assertEqual(sprint_metrics.completed_task_count, 1)
        self.assertEqual(sprint_metrics.velocity_effort, Decimal("8.00"))
        self.assertEqual(sprint_metrics.completed_actual_effort, Decimal("9.00"))
