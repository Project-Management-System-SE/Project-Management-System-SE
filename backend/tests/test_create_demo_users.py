from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from projects.models import Project, ProjectMembership

User = get_user_model()


class CreateDemoUsersCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_creates_active_role_accounts_and_demo_project_idempotently(self):
        call_command("create_demo_users", "--with-demo-project", stdout=StringIO())
        call_command("create_demo_users", "--with-demo-project", stdout=StringIO())

        admin = User.objects.get(email="admin@example.com")
        self.assertTrue(admin.is_admin)
        self.assertTrue(admin.check_password("Admin@12345"))
        for email in ["manager@example.com", "member@example.com", "outsider@example.com"]:
            user = User.objects.get(email=email)
            self.assertTrue(user.is_active)
            self.assertFalse(user.is_admin)

        project = Project.objects.get(name="Sprint Analytics Demo")
        roles = dict(project.memberships.values_list("user__email", "project_role"))
        self.assertEqual(roles["manager@example.com"], ProjectMembership.Role.PROJECT_MANAGER)
        self.assertEqual(roles["member@example.com"], ProjectMembership.Role.TEAM_MEMBER)
        self.assertNotIn("outsider@example.com", roles)
        self.assertEqual(Project.objects.filter(name="Sprint Analytics Demo").count(), 1)

    @override_settings(DEBUG=False)
    def test_production_requires_explicit_admin_password(self):
        with self.assertRaises(CommandError):
            call_command("create_demo_users", stdout=StringIO())
        self.assertFalse(User.objects.filter(email="admin@example.com").exists())

        call_command("create_demo_users", "--admin-password", "Chosen-Secret-1", stdout=StringIO())
        self.assertTrue(User.objects.get(email="admin@example.com").check_password("Chosen-Secret-1"))
