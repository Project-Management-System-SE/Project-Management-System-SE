from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from projects.forms import MilestoneForm, SprintForm
from projects.models import (
    Milestone,
    Project,
    ProjectMembership,
    Sprint,
    SprintTaskHistory,
)
from tasks.models import Task


class SprintManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            password="Password123!",
        )
        self.manager = User.objects.create_user(
            email="manager@example.com",
            username="manager",
            full_name="Manager",
            password="Password123!",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Member",
            password="Password123!",
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com",
            username="outsider",
            full_name="Outsider",
            password="Password123!",
        )
        self.project = Project.objects.create(name="Planning", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.owner,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.manager,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )

    def sprint_payload(self, **overrides):
        payload = {
            "name": "Sprint 1",
            "goal": "Deliver planning",
            "start_date": "2026-11-01",
            "end_date": "2026-11-14",
            "status": Sprint.Status.PLANNED,
        }
        payload.update(overrides)
        return payload

    def test_sprint_and_milestone_persist_with_constraints(self):
        sprint = Sprint.objects.create(
            project=self.project,
            name="Sprint 1",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
            created_by=self.owner,
        )
        milestone = Milestone.objects.create(
            project=self.project,
            name="Release",
            target_date=date(2026, 11, 30),
        )

        self.assertEqual(sprint.status, Sprint.Status.PLANNED)
        self.assertEqual(milestone.target_date, date(2026, 11, 30))
        with self.assertRaises(ValidationError):
            Sprint(
                project=self.project,
                name="Invalid",
                start_date=date(2026, 11, 15),
                end_date=date(2026, 11, 1),
            ).full_clean()

    def test_only_one_active_sprint_per_project(self):
        Sprint.objects.create(
            project=self.project,
            name="Active 1",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
            status=Sprint.Status.ACTIVE,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sprint.objects.bulk_create(
                    [
                        Sprint(
                            project=self.project,
                            name="Active 2",
                            start_date=date(2026, 11, 15),
                            end_date=date(2026, 11, 28),
                            status=Sprint.Status.ACTIVE,
                        )
                    ]
                )

    def test_forms_validate_dates_and_project_scope(self):
        invalid_sprint = SprintForm(
            data=self.sprint_payload(
                start_date="2026-11-14",
                end_date="2026-11-01",
            ),
            project=self.project,
        )
        invalid_milestone = MilestoneForm(
            data={
                "name": "Release",
                "description": "",
                "target_date": "2026-11-30",
                "status": Milestone.Status.PLANNED,
            },
            project=self.project,
        )

        self.assertFalse(invalid_sprint.is_valid())
        self.assertIn("end_date", invalid_sprint.errors)
        self.assertTrue(invalid_milestone.is_valid())

    def test_task_sprint_and_milestone_must_match_project(self):
        other_project = Project.objects.create(name="Other", owner=self.outsider)
        sprint = Sprint.objects.create(
            project=other_project,
            name="Other sprint",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
        )
        milestone = Milestone.objects.create(project=other_project, name="Other milestone")
        task = Task(
            project=self.project,
            title="Cross-project task",
            created_by=self.owner,
            sprint=sprint,
        )
        with self.assertRaises(ValidationError):
            task.full_clean()
        task.sprint = None
        task.milestone = milestone
        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_manager_can_create_activate_and_close_with_backlog_carry_over(self):
        self.client.force_login(self.manager)
        create_response = self.client.post(
            reverse("projects:sprint-create", args=[self.project.pk]),
            self.sprint_payload(),
        )
        self.assertRedirects(
            create_response,
            reverse(
                "projects:sprint-detail",
                args=[self.project.pk, Sprint.objects.get(project=self.project).pk],
            ),
        )
        sprint = Sprint.objects.get(project=self.project)
        task = Task.objects.create(
            project=self.project,
            title="Incomplete",
            created_by=self.owner,
            sprint=sprint,
        )
        done_task = Task.objects.create(
            project=self.project,
            title="Complete",
            created_by=self.owner,
            status=Task.Status.DONE,
            sprint=sprint,
        )
        self.client.post(
            reverse("projects:sprint-activate", args=[self.project.pk, sprint.pk])
        )
        close_response = self.client.post(
            reverse("projects:sprint-close", args=[self.project.pk, sprint.pk]),
            {"note": "Plan again"},
        )

        self.assertRedirects(
            close_response,
            reverse("projects:sprint-detail", args=[self.project.pk, sprint.pk]),
        )
        sprint.refresh_from_db()
        task.refresh_from_db()
        done_task.refresh_from_db()
        self.assertEqual(sprint.status, Sprint.Status.COMPLETED)
        self.assertIsNone(task.sprint)
        self.assertEqual(done_task.sprint_id, sprint.pk)
        history = SprintTaskHistory.objects.get(task=task)
        self.assertEqual(history.event_type, "RETURN_TO_BACKLOG")
        self.assertEqual(history.actor_id, self.manager.pk)

    def test_cross_project_carry_over_is_rejected(self):
        sprint = Sprint.objects.create(
            project=self.project,
            name="Active",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
            status=Sprint.Status.ACTIVE,
        )
        other_project = Project.objects.create(name="Other", owner=self.outsider)
        destination = Sprint.objects.create(
            project=other_project,
            name="Other destination",
            start_date=date(2026, 11, 15),
            end_date=date(2026, 11, 28),
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("projects:sprint-close", args=[self.project.pk, sprint.pk]),
            {"carry_over_sprint": destination.pk},
        )
        self.assertEqual(response.status_code, 404)
        sprint.refresh_from_db()
        self.assertEqual(sprint.status, Sprint.Status.ACTIVE)

    def test_member_can_view_but_not_manage_planning(self):
        sprint = Sprint.objects.create(
            project=self.project,
            name="Visible",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
        )
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(
                reverse("projects:sprint-list", args=[self.project.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                reverse("projects:sprint-activate", args=[self.project.pk, sprint.pk])
            ).status_code,
            403,
        )

    def test_sprint_effort_and_milestone_progress_are_displayed(self):
        sprint = Sprint.objects.create(
            project=self.project,
            name="Metrics",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
        )
        milestone = Milestone.objects.create(project=self.project, name="Release")
        Task.objects.create(
            project=self.project,
            title="Done",
            created_by=self.owner,
            status=Task.Status.DONE,
            sprint=sprint,
            milestone=milestone,
            estimated_effort=Decimal("2.50"),
            actual_effort=Decimal("3.00"),
        )
        Task.objects.create(
            project=self.project,
            title="Todo",
            created_by=self.owner,
            sprint=sprint,
            milestone=milestone,
            estimated_effort=Decimal("1.50"),
        )
        self.client.force_login(self.member)
        response = self.client.get(
            reverse("projects:sprint-list", args=[self.project.pk])
        )

        self.assertContains(response, "4.00 hours")
        self.assertContains(response, "3.00 hours")
        self.assertContains(response, "1 of 2 tasks completed")
        self.assertContains(response, "(50%)")

    def test_dashboard_displays_active_sprint_effort_summary(self):
        sprint = Sprint.objects.create(
            project=self.project,
            name="Current sprint",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 14),
            status=Sprint.Status.ACTIVE,
        )
        Task.objects.create(
            project=self.project,
            title="Dashboard task",
            created_by=self.owner,
            sprint=sprint,
            estimated_effort=Decimal("2.00"),
            actual_effort=Decimal("1.25"),
        )

        self.client.force_login(self.member)
        response = self.client.get(reverse("projects:dashboard"))

        self.assertContains(response, "Current sprint")
        self.assertContains(response, "2.00 estimated")
        self.assertContains(response, "1.25 actual hours")
