"""Create a fictional demo workspace in a Render PostgreSQL database.

Run from the repository root with:
    .venv\\Scripts\\python.exe backend\\seed_render_demo.py

The external database URL is requested with hidden input and is never printed.
"""

import getpass
import os
import secrets
from datetime import timedelta
from decimal import Decimal


def main():
    database_url = getpass.getpass("Render External Database URL (input hidden): ").strip()
    if not database_url:
        raise SystemExit("No database URL entered; nothing was changed.")

    os.environ["DATABASE_URL"] = database_url
    os.environ["DJANGO_DEBUG"] = "true"
    os.environ.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(50))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from django.db import connection, transaction
    from django.utils import timezone

    from accounts.models import User
    from projects.models import Milestone, Project, ProjectMembership, Sprint
    from tasks.audit import record_audit
    from tasks.models import AuditLog, Task, TaskComment, TaskLabel
    from tasks.notifications import notify_task_assignment

    if connection.vendor != "postgresql":
        raise SystemExit("Refusing to write: the supplied URL did not connect to PostgreSQL.")

    people_spec = [
        ("Demo Administrator", "admin@fieldwork.example.com", "demo_admin"),
        ("Alex Morgan", "alex@fieldwork.example.com", "alex_morgan"),
        ("Priya Shah", "priya@fieldwork.example.com", "priya_shah"),
        ("Jordan Lee", "jordan@fieldwork.example.com", "jordan_lee"),
    ]
    emails = [person[1] for person in people_spec]
    project_name = "Employee Onboarding Portal (Demo)"
    if User.objects.filter(email__in=emails).exists():
        raise SystemExit("A demo email already exists in this database; nothing was changed.")
    if Project.objects.filter(name=project_name).exists():
        raise SystemExit("The demo project already exists in this database; nothing was changed.")

    today = timezone.localdate()
    credentials = {}
    with transaction.atomic():
        people = []
        for index, (full_name, email, username) in enumerate(people_spec):
            password = secrets.token_urlsafe(18)
            user = User.objects.create_user(
                email=email,
                username=username,
                full_name=full_name,
                password=password,
                is_staff=(index == 0),
                is_superuser=(index == 0),
            )
            people.append(user)
            credentials[email] = password

        admin_user, alex, priya, jordan = people
        project = Project.objects.create(
            name=project_name,
            description=(
                "Build a secure, responsive portal that helps new employees complete "
                "onboarding tasks and helps the People Operations team track progress."
            ),
            owner=admin_user,
            status=Project.Status.ACTIVE,
            start_date=today,
            due_date=today + timedelta(days=30),
        )
        ProjectMembership.objects.create(
            project=project,
            user=admin_user,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        for employee in (alex, priya, jordan):
            ProjectMembership.objects.create(
                project=project,
                user=employee,
                project_role=ProjectMembership.Role.TEAM_MEMBER,
            )

        sprint = Sprint.objects.create(
            project=project,
            name="Sprint 1 - Onboarding MVP",
            goal="Deliver the first usable employee onboarding flow.",
            start_date=today,
            end_date=today + timedelta(days=13),
            status=Sprint.Status.ACTIVE,
            created_by=admin_user,
        )
        milestone = Milestone.objects.create(
            project=project,
            name="Onboarding MVP ready",
            description="Complete the core onboarding experience for an internal pilot.",
            target_date=today + timedelta(days=30),
            status=Milestone.Status.IN_PROGRESS,
        )

        label_names = ("backend", "frontend", "design", "qa", "security")
        labels = {
            name: TaskLabel.objects.create(project=project, name=name)
            for name in label_names
        }
        task_specs = [
            (
                "Set up project structure and CI checks",
                "Create the application skeleton, environment configuration, and automated CI checks.",
                alex, Task.Status.TODO, Task.Priority.HIGH, Decimal("5.00"), 4, ("backend",),
            ),
            (
                "Design onboarding dashboard and task flow",
                "Create responsive dashboard and onboarding checklist screens for employees.",
                priya, Task.Status.IN_PROGRESS, Task.Priority.HIGH, Decimal("6.00"), 6,
                ("design", "frontend"),
            ),
            (
                "Implement sign-in and role permissions",
                "Add secure sign-in and role checks for employees and People Operations admins.",
                jordan, Task.Status.TODO, Task.Priority.CRITICAL, Decimal("8.00"), 8,
                ("backend", "security"),
            ),
            (
                "Build onboarding checklist and progress tracking",
                "Allow employees to complete assigned onboarding steps and record progress.",
                alex, Task.Status.TODO, Task.Priority.MEDIUM, Decimal("5.00"), 11,
                ("backend", "frontend"),
            ),
            (
                "Run acceptance checks for the employee pilot",
                "Verify onboarding completion, permissions, and dashboard behavior with sample users.",
                priya, Task.Status.TODO, Task.Priority.MEDIUM, Decimal("4.00"), 13,
                ("qa",),
            ),
            (
                "Prepare pilot release and handover notes",
                "Document the pilot setup and prepare a short handover for People Operations.",
                jordan, Task.Status.BACKLOG, Task.Priority.LOW, Decimal("3.00"), 18,
                ("qa",),
            ),
        ]

        tasks = []
        for title, description, assignee, status, priority, estimate, due_days, task_labels in task_specs:
            task = Task.objects.create(
                project=project,
                sprint=sprint,
                milestone=milestone,
                title=title,
                description=description,
                assignee=assignee,
                created_by=admin_user,
                status=status,
                priority=priority,
                estimated_effort=estimate,
                due_date=today + timedelta(days=due_days),
            )
            task.labels.set([labels[name] for name in task_labels])
            record_audit(admin_user, AuditLog.Action.CREATE, task)
            notify_task_assignment(task)
            tasks.append(task)

        record_audit(admin_user, AuditLog.Action.CREATE, project)
        TaskComment.objects.create(
            task=tasks[0],
            author=admin_user,
            content=(
                "Welcome to the demo project. Please add progress updates here as "
                "work moves through the board."
            ),
        )

    print("Created demo accounts (temporary passwords):")
    for full_name, email, _username in people_spec:
        print(f"{full_name} | {email} | {credentials[email]}")
    print(f"Project: {project.name}")
    print(f"Team: {project.memberships.count()} people; tasks: {len(tasks)}")
    print(f"Planning: {sprint.name}; milestone: {milestone.name}")
    print("Each employee has assigned work; notifications and activity history were added.")
    os.environ.pop("DATABASE_URL", None)


if __name__ == "__main__":
    main()
