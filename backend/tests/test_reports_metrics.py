import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from projects.models import Project, Sprint
from projects.reports import (
    build_sprint_burndown,
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
        today = datetime.date.today()
        sprint = Sprint.objects.create(
            project=self.project,
            name="Sprint 1",
            status=Sprint.Status.COMPLETED,
            start_date=today - datetime.timedelta(days=14),
            end_date=today,
        )
        Task.objects.create(
            title="Sprint Task",
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            status=Task.Status.DONE,
            estimated_effort=Decimal("8.25"),
            actual_effort=Decimal("10.00"),
        )
        velocity = get_sprint_velocity_metrics(self.project)
        self.assertEqual(velocity["closed_sprint_count"], 1)
        self.assertEqual(velocity["average_velocity"], Decimal("8.25"))

    def test_velocity_uses_only_completed_estimates_and_marks_missing_effort(self):
        today = datetime.date.today()
        sprint = Sprint.objects.create(
            project=self.project,
            name="Incomplete estimates",
            status=Sprint.Status.COMPLETED,
            start_date=today - datetime.timedelta(days=7),
            end_date=today,
        )
        Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Estimated complete",
            status=Task.Status.DONE,
            estimated_effort=Decimal("2.35"),
            actual_effort=Decimal("99.00"),
        )
        Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Unestimated complete",
            status=Task.Status.DONE,
            actual_effort=Decimal("7.00"),
        )
        Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Not complete",
            status=Task.Status.IN_PROGRESS,
            estimated_effort=Decimal("100.00"),
        )

        velocity = get_sprint_velocity_metrics(self.project)
        sprint_metrics = velocity["sprints"][0]

        self.assertIsNone(sprint_metrics["velocity"])
        self.assertEqual(sprint_metrics["known_estimated_effort"], Decimal("2.35"))
        self.assertEqual(sprint_metrics["completed_tasks"], 2)
        self.assertEqual(sprint_metrics["estimated_task_count"], 1)
        self.assertEqual(sprint_metrics["missing_estimate_count"], 1)
        self.assertEqual(sprint_metrics["completed_effort"], Decimal("106.00"))
        self.assertIsNone(velocity["average_velocity"])
        self.assertEqual(velocity["incomplete_sprint_count"], 1)

    def test_velocity_average_excludes_sprints_with_missing_completed_estimates(self):
        today = datetime.date.today()
        incomplete = Sprint.objects.create(
            project=self.project,
            name="Incomplete",
            status=Sprint.Status.COMPLETED,
            start_date=today - datetime.timedelta(days=14),
            end_date=today - datetime.timedelta(days=8),
        )
        complete = Sprint.objects.create(
            project=self.project,
            name="Complete",
            status=Sprint.Status.COMPLETED,
            start_date=today - datetime.timedelta(days=7),
            end_date=today,
        )
        Task.objects.create(
            project=self.project,
            sprint=incomplete,
            created_by=self.user,
            title="Missing estimate",
            status=Task.Status.DONE,
        )
        Task.objects.create(
            project=self.project,
            sprint=complete,
            created_by=self.user,
            title="Estimated task",
            status=Task.Status.DONE,
            estimated_effort=Decimal("3.45"),
        )

        velocity = get_sprint_velocity_metrics(self.project)

        self.assertEqual(velocity["average_velocity"], Decimal("3.45"))
        self.assertEqual(velocity["velocity_sprint_count"], 1)
        self.assertEqual(velocity["incomplete_sprint_count"], 1)

    def test_burndown_ideal_and_actual_remaining_use_saved_effort_and_dates(self):
        start = datetime.date(2026, 11, 1)
        sprint = Sprint.objects.create(
            project=self.project,
            name="Burndown",
            status=Sprint.Status.COMPLETED,
            start_date=start,
            end_date=start + datetime.timedelta(days=4),
        )
        completed = Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Completed",
            status=Task.Status.DONE,
            estimated_effort=Decimal("5.25"),
        )
        Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Remaining",
            status=Task.Status.IN_PROGRESS,
            estimated_effort=Decimal("2.75"),
        )
        Task.objects.filter(pk=completed.pk).update(
            completed_at=timezone.make_aware(
                datetime.datetime(2026, 11, 3, 12, 0)
            )
        )

        burndown = build_sprint_burndown(sprint, as_of=sprint.end_date)

        self.assertTrue(burndown["chart_available"])
        self.assertEqual(burndown["estimated_effort"], Decimal("8.00"))
        self.assertEqual(burndown["current_remaining_effort"], Decimal("2.75"))
        self.assertEqual(len(burndown["chart_points"]), 5)
        self.assertEqual(
            [point["ideal_remaining"] for point in burndown["chart_points"]],
            [
                Decimal("8.00"),
                Decimal("6.00"),
                Decimal("4.00"),
                Decimal("2.00"),
                Decimal("0.00"),
            ],
        )
        self.assertEqual(
            [point["actual_remaining"] for point in burndown["chart_points"]],
            [
                Decimal("8.00"),
                Decimal("8.00"),
                Decimal("2.75"),
                Decimal("2.75"),
                Decimal("2.75"),
            ],
        )

    def test_burndown_excludes_completions_after_sprint_and_includes_before_start(self):
        start = datetime.date(2026, 11, 1)
        sprint = Sprint.objects.create(
            project=self.project,
            name="Date boundaries",
            status=Sprint.Status.COMPLETED,
            start_date=start,
            end_date=start + datetime.timedelta(days=2),
        )
        completed_before = Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Completed before start",
            status=Task.Status.DONE,
            estimated_effort=Decimal("2.00"),
        )
        completed_after = Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Completed after end",
            status=Task.Status.DONE,
            estimated_effort=Decimal("3.00"),
        )
        Task.objects.filter(pk=completed_before.pk).update(
            completed_at=timezone.make_aware(
                datetime.datetime(2026, 10, 31, 12, 0)
            )
        )
        Task.objects.filter(pk=completed_after.pk).update(
            completed_at=timezone.make_aware(
                datetime.datetime(2026, 11, 5, 12, 0)
            )
        )

        burndown = build_sprint_burndown(sprint, as_of=sprint.end_date)

        self.assertEqual(
            [point["actual_remaining"] for point in burndown["chart_points"]],
            [Decimal("3.00")] * 3,
        )

    def test_burndown_uses_local_date_for_aware_completion_timestamps(self):
        from zoneinfo import ZoneInfo

        start = datetime.date(2026, 11, 1)
        sprint = Sprint.objects.create(
            project=self.project,
            name="Timezone",
            status=Sprint.Status.COMPLETED,
            start_date=start,
            end_date=start + datetime.timedelta(days=2),
        )
        completed = Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Timezone completed",
            status=Task.Status.DONE,
            estimated_effort=Decimal("4.00"),
        )
        Task.objects.filter(pk=completed.pk).update(
            completed_at=timezone.make_aware(
                datetime.datetime(2026, 11, 2, 1, 0),
                timezone=datetime.timezone.utc,
            )
        )

        with timezone.override(ZoneInfo("America/Los_Angeles")):
            burndown = build_sprint_burndown(sprint, as_of=sprint.end_date)

        self.assertEqual(
            [point["actual_remaining"] for point in burndown["chart_points"]],
            [Decimal("0.00"), Decimal("0.00"), Decimal("0.00")],
        )

    def test_burndown_handles_same_day_sprint_and_missing_estimates(self):
        today = datetime.date.today()
        sprint = Sprint.objects.create(
            project=self.project,
            name="One day",
            status=Sprint.Status.COMPLETED,
            start_date=today,
            end_date=today,
        )
        completed = Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="Zero estimate",
            status=Task.Status.DONE,
            estimated_effort=Decimal("0.00"),
        )
        Task.objects.create(
            project=self.project,
            sprint=sprint,
            created_by=self.user,
            title="No estimate",
        )
        Task.objects.filter(pk=completed.pk).update(
            completed_at=timezone.now()
        )

        burndown = build_sprint_burndown(sprint, as_of=today)

        self.assertTrue(burndown["chart_available"])
        self.assertEqual(burndown["missing_estimate_count"], 1)
        self.assertEqual(len(burndown["chart_points"]), 1)
        self.assertEqual(
            burndown["chart_points"][0]["ideal_remaining"], Decimal("0.00")
        )
        self.assertEqual(
            burndown["chart_points"][0]["actual_remaining"], Decimal("0.00")
        )

    def test_burndown_empty_new_and_without_completion_history_states(self):
        today = datetime.date.today()
        empty = Sprint.objects.create(
            project=self.project,
            name="Empty",
            start_date=today,
            end_date=today,
        )
        self.assertFalse(build_sprint_burndown(empty, as_of=today)["chart_available"])

        planned = Sprint.objects.create(
            project=self.project,
            name="New",
            start_date=today,
            end_date=today + datetime.timedelta(days=2),
        )
        Task.objects.create(
            project=self.project,
            sprint=planned,
            created_by=self.user,
            title="No estimate",
        )
        no_estimates = build_sprint_burndown(planned, as_of=today)
        self.assertEqual(no_estimates["estimated_task_count"], 0)
        self.assertFalse(no_estimates["chart_available"])

        Task.objects.create(
            project=self.project,
            sprint=planned,
            created_by=self.user,
            title="Incomplete estimate",
            estimated_effort=Decimal("2.00"),
        )
        no_history = build_sprint_burndown(planned, as_of=today)
        self.assertFalse(no_history["sprint_started"])
        self.assertFalse(no_history["has_completion_data"])
        self.assertFalse(no_history["chart_available"])

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
