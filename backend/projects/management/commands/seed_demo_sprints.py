"""Create a demo project with sprints so the burndown and velocity charts have data.

Usage (from backend/):
    python manage.py seed_demo_sprints --owner admin@example.com
    python manage.py seed_demo_sprints --owner admin@example.com --member a@x.com --member b@x.com

It creates the project "Sprint Analytics Demo" with:
  * Sprint 1 and Sprint 2 - completed (velocity history),
  * Sprint 3 - active, spanning today (burndown chart),
and tasks with estimates whose completion dates fall inside each sprint.
Dates are relative to today, so the active sprint is always "in progress".
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from projects.models import Project, ProjectMembership, Sprint
from tasks.models import Task

PROJECT_NAME = "Sprint Analytics Demo"

# (title, estimate hours, priority, final status, completion day offset from sprint start or None)
SPRINTS = [
    {
        "name": "Sprint 1 - Foundations",
        "goal": "Set up the project skeleton, authentication and project creation.",
        "start": -35, "length": 13, "status": Sprint.Status.COMPLETED,
        "tasks": [
            ("Set up repository and CI checks", 3, "HIGH", "DONE", 1),
            ("Design database schema", 5, "HIGH", "DONE", 3),
            ("User registration and login", 8, "CRITICAL", "DONE", 6),
            ("Project creation form", 5, "MEDIUM", "DONE", 8),
            ("Base layout and navigation", 3, "MEDIUM", "DONE", 10),
            ("Unit tests for accounts", 2, "LOW", "DONE", 12),
        ],
    },
    {
        "name": "Sprint 2 - Task Management",
        "goal": "Tasks, Kanban board and workflow rules.",
        "start": -21, "length": 13, "status": Sprint.Status.COMPLETED,
        "tasks": [
            ("Task model and forms", 5, "HIGH", "DONE", 2),
            ("Kanban board with drag and drop", 8, "CRITICAL", "DONE", 5),
            ("Review-before-Done workflow rule", 3, "HIGH", "DONE", 6),
            ("Task labels and filters", 5, "MEDIUM", "DONE", 8),
            ("Task comments", 3, "MEDIUM", "DONE", 10),
            ("Integration tests for the board", 5, "MEDIUM", "DONE", 12),
        ],
    },
    {
        "name": "Sprint 3 - Analytics and Release",
        "goal": "Dashboard analytics, reports, notifications and deployment.",
        "start": -7, "length": 13, "status": Sprint.Status.ACTIVE,
        "tasks": [
            ("Sprint burndown chart", 5, "HIGH", "DONE", 1),
            ("Velocity report", 3, "MEDIUM", "DONE", 3),
            ("Task notifications", 5, "MEDIUM", "DONE", 4),
            ("CSV report export", 3, "LOW", "DONE", 6),
            ("Activity audit log", 5, "MEDIUM", "REVIEW", None),
            ("REST API documentation", 3, "LOW", "IN_PROGRESS", None),
            ("Production deployment", 8, "CRITICAL", "IN_PROGRESS", None),
            ("Final acceptance testing", 5, "HIGH", "TODO", None),
        ],
    },
]


class Command(BaseCommand):
    help = "Create a demo project with completed and active sprints for burndown/velocity charts."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Email of an existing user who will own the demo project.")
        parser.add_argument("--member", action="append", default=[],
                            help="Email of an existing user to add as a team member (repeatable).")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            owner = User.objects.get(email__iexact=options["owner"])
        except User.DoesNotExist as error:
            raise CommandError(f"No user with email {options['owner']!r}. Create the account first.") from error

        members = []
        for email in options["member"]:
            try:
                members.append(User.objects.get(email__iexact=email))
            except User.DoesNotExist as error:
                raise CommandError(f"No user with email {email!r}.") from error

        if Project.objects.filter(name=PROJECT_NAME).exists():
            raise CommandError(f"A project named {PROJECT_NAME!r} already exists; nothing was changed.")

        today = timezone.localdate()
        with transaction.atomic():
            project = Project.objects.create(
                name=PROJECT_NAME,
                description="Demo data for sprint burndown and velocity charts.",
                owner=owner,
                status=Project.Status.ACTIVE,
                start_date=today - timedelta(days=35),
                due_date=today + timedelta(days=20),
            )
            ProjectMembership.objects.update_or_create(
                project=project, user=owner,
                defaults={"project_role": ProjectMembership.Role.PROJECT_MANAGER},
            )
            for member in members:
                if member != owner:
                    ProjectMembership.objects.get_or_create(
                        project=project, user=member,
                        defaults={"project_role": ProjectMembership.Role.TEAM_MEMBER},
                    )

            assignees = [owner] + [m for m in members if m != owner]
            task_count = 0
            for spec in SPRINTS:
                start = today + timedelta(days=spec["start"])
                sprint = Sprint.objects.create(
                    project=project,
                    name=spec["name"],
                    goal=spec["goal"],
                    start_date=start,
                    end_date=start + timedelta(days=spec["length"]),
                    status=spec["status"],
                    created_by=owner,
                )
                for title, estimate, priority, status, done_offset in spec["tasks"]:
                    completed_at = None
                    if done_offset is not None:
                        completed_at = timezone.make_aware(
                            datetime.combine(start + timedelta(days=done_offset), time(16, 0))
                        )
                    Task.objects.create(
                        project=project,
                        sprint=sprint,
                        title=title,
                        description=f"{title} ({spec['name']}).",
                        priority=priority,
                        status=status,
                        estimated_effort=Decimal(estimate),
                        actual_effort=Decimal(estimate) + Decimal("0.5") if completed_at else None,
                        completed_at=completed_at,
                        assignee=assignees[task_count % len(assignees)],
                        created_by=owner,
                        due_date=start + timedelta(days=spec["length"]),
                    )
                    task_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created {PROJECT_NAME!r} (id {project.pk}) with {len(SPRINTS)} sprints and {task_count} tasks."
        ))
