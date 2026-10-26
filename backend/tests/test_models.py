from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from projects.models import Project, ProjectMembership


class UserModelTests(TestCase):
    def test_create_user_requires_email_username_and_full_name(self):
        missing_fields = (
            {"email": "", "username": "member", "full_name": "Team Member"},
            {"email": "member@example.com", "username": "", "full_name": "Team Member"},
            {"email": "member@example.com", "username": "member", "full_name": ""},
        )

        for fields in missing_fields:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    User.objects.create_user(**fields, password="safe-password-123")

    def test_create_user_hashes_the_password(self):
        user = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Team Member",
            password="safe-password-123",
        )

        self.assertNotEqual(user.password, "safe-password-123")
        self.assertTrue(user.check_password("safe-password-123"))
        self.assertEqual(user.email, "member@example.com")
        self.assertFalse(user.is_admin)

    def test_create_superuser_has_admin_flags(self):
        user = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="safe-password-123",
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_admin)

    def test_create_superuser_rejects_non_admin_flags(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com",
                username="admin",
                full_name="System Admin",
                password="safe-password-123",
                is_staff=False,
            )

    def test_email_is_the_authentication_identifier(self):
        user = User.objects.create_user(
            email="login@example.com",
            username="login-user",
            full_name="Login User",
            password="safe-password-123",
        )

        self.assertEqual(user.get_username(), "login@example.com")


class ProjectModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="safe-password-123",
        )

    def test_project_defaults_to_planned_status(self):
        project = Project.objects.create(name="PMS", owner=self.user)

        self.assertEqual(project.status, Project.Status.PLANNED)
        self.assertEqual(str(project), "PMS")

    def test_due_date_cannot_precede_start_date(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Project.objects.create(
                    name="Invalid dates",
                    owner=self.user,
                    start_date=date(2026, 10, 10),
                    due_date=date(2026, 10, 1),
                )

    def test_project_accepts_missing_dates(self):
        project = Project.objects.create(name="Undated project", owner=self.user)

        self.assertIsNone(project.start_date)
        self.assertIsNone(project.due_date)

    def test_due_date_may_match_start_date(self):
        same_day = date(2026, 10, 10)
        project = Project.objects.create(
            name="Single-day project",
            owner=self.user,
            start_date=same_day,
            due_date=same_day,
        )

        self.assertEqual(project.start_date, same_day)
        self.assertEqual(project.due_date, same_day)

    def test_membership_is_unique_per_project_and_user(self):
        project = Project.objects.create(name="PMS", owner=self.user)
        ProjectMembership.objects.create(
            project=project,
            user=self.user,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProjectMembership.objects.create(
                    project=project,
                    user=self.user,
                    project_role=ProjectMembership.Role.TEAM_MEMBER,
                )
