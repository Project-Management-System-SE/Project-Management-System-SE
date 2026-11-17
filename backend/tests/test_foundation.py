from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, override_settings
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

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_http_requests_redirect_to_https(self):
        response = Client().get(reverse("login"))

        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            f"https://testserver{reverse('login')}",
        )

    @override_settings(CSRF_COOKIE_SECURE=True)
    def test_csrf_cookie_is_marked_secure_when_configured(self):
        response = Client().get(reverse("login"), secure=True)

        self.assertTrue(response.cookies[settings.CSRF_COOKIE_NAME]["secure"])


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

    def test_auth_routes_reverse(self):
        self.assertEqual(reverse("login"), "/accounts/login/")
        self.assertEqual(reverse("logout"), "/accounts/logout/")
