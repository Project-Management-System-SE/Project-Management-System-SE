"""Create the shared demo accounts (one per role) and, optionally, the demo project.

Usage (from backend/):
    python manage.py create_demo_users --with-demo-project
    python manage.py create_demo_users --admin-password "<secret>" --with-demo-project   # production

Accounts (all active, so no confirmation email is needed):
    admin@example.com     system Admin
    manager@example.com   Project Manager of the demo project
    member@example.com    Team Member of the demo project
    outsider@example.com  no project access (shows the 404 protection)

Safe to run more than once: existing accounts and the demo project are left as they are.
The repository is public, so outside DEBUG the admin password must be passed explicitly
instead of using the documented default.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from projects.models import Project, ProjectMembership

DEFAULT_ADMIN_PASSWORD = "Admin@12345"
DEMO_USERS = [
    # (email, username, full name, default password)
    ("manager@example.com", "manager", "Priya Manager", "Manager@12345"),
    ("member@example.com", "member", "Rahul Member", "Member@12345"),
    ("outsider@example.com", "outsider", "Outside User", "Outsider@12345"),
]
DEMO_PROJECT_NAME = "Sprint Analytics Demo"


class Command(BaseCommand):
    help = "Create shared demo accounts for each role, and optionally the demo project."

    def add_arguments(self, parser):
        parser.add_argument("--admin-password", help="Password for admin@example.com (required outside DEBUG).")
        parser.add_argument(
            "--with-demo-project",
            action="store_true",
            help="Also create the 'Sprint Analytics Demo' project with sprints and tasks.",
        )

    def handle(self, *args, **options):
        admin_password = options["admin_password"]
        if not admin_password:
            if not settings.DEBUG:
                raise CommandError(
                    "Outside DEBUG, pass --admin-password: the default admin password is "
                    "published in this public repository."
                )
            admin_password = DEFAULT_ADMIN_PASSWORD

        User = get_user_model()
        if User.objects.filter(email__iexact="admin@example.com").exists():
            self.stdout.write("admin@example.com already exists (unchanged).")
        else:
            User.objects.create_superuser(
                email="admin@example.com", username="admin", full_name="Admin User", password=admin_password
            )
            self.stdout.write(self.style.SUCCESS("Created admin@example.com"))

        for email, username, full_name, password in DEMO_USERS:
            if User.objects.filter(email__iexact=email).exists():
                self.stdout.write(f"{email} already exists (unchanged).")
                continue
            User.objects.create_user(email=email, username=username, full_name=full_name, password=password)
            self.stdout.write(self.style.SUCCESS(f"Created {email}"))

        if not options["with_demo_project"]:
            return

        if Project.objects.filter(name=DEMO_PROJECT_NAME).exists():
            self.stdout.write(f"Project {DEMO_PROJECT_NAME!r} already exists (unchanged).")
        else:
            call_command(
                "seed_demo_sprints",
                owner="admin@example.com",
                member=["manager@example.com", "member@example.com"],
                stdout=self.stdout,
            )

        project = Project.objects.get(name=DEMO_PROJECT_NAME)
        ProjectMembership.objects.update_or_create(
            project=project,
            user=User.objects.get(email__iexact="manager@example.com"),
            defaults={"project_role": ProjectMembership.Role.PROJECT_MANAGER},
        )
        self.stdout.write(self.style.SUCCESS("manager@example.com is Project Manager of the demo project."))
