from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve, reverse

from projects import views


class SettingsTests(SimpleTestCase):
    def test_documented_apps_are_installed(self):
        for app_name in ("accounts", "projects", "tasks"):
            self.assertIn(app_name, settings.INSTALLED_APPS)

    def test_custom_user_model_is_configured(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")

    def test_root_template_and_static_directories_are_configured(self):
        expected_templates = Path(settings.PROJECT_ROOT) / "templates"
        expected_static = Path(settings.PROJECT_ROOT) / "static"

        self.assertIn(expected_templates, [Path(path) for path in settings.TEMPLATES[0]["DIRS"]])
        self.assertIn(expected_static, [Path(path) for path in settings.STATICFILES_DIRS])

    def test_development_secret_key_is_not_empty(self):
        self.assertTrue(settings.SECRET_KEY)


class UrlTests(SimpleTestCase):
    def test_dashboard_routes_resolve(self):
        self.assertIs(resolve("/").func, views.dashboard)
        self.assertIs(resolve("/dashboard/").func, views.dashboard)

    def test_project_routes_resolve(self):
        self.assertIs(resolve("/projects/").func, views.project_list)
        self.assertIs(resolve("/projects/new/").func, views.project_create)

    def test_named_project_routes_reverse(self):
        self.assertEqual(reverse("projects:dashboard"), "/")
        self.assertEqual(reverse("projects:project-list"), "/projects/")
        self.assertEqual(reverse("projects:project-create"), "/projects/new/")
