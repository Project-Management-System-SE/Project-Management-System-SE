import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from django.conf import settings
from django.db import OperationalError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse

from config import health
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

    def test_postgres_database_url_enables_production_database_and_secure_defaults(self):
        environment = os.environ.copy()
        environment.update(
            {
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "test-deployment-secret-with-adequate-length-0123456789",
                "DATABASE_URL": "postgresql://pms_user:db-password@db.example:5432/pms",
            }
        )
        script = (
            "import json; from django.conf import settings; "
            "print(json.dumps({"
            "'debug': settings.DEBUG, "
            "'database_engine': settings.DATABASES['default']['ENGINE'], "
            "'database_name': settings.DATABASES['default']['NAME'], "
            "'secure_redirect': settings.SECURE_SSL_REDIRECT, "
            "'session_cookie_secure': settings.SESSION_COOKIE_SECURE, "
            "'csrf_cookie_secure': settings.CSRF_COOKIE_SECURE, "
            "'hsts_seconds': settings.SECURE_HSTS_SECONDS, "
            "'static_storage': settings.STORAGES['staticfiles']['BACKEND']"
            "}))"
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        production_settings = json.loads(result.stdout)
        self.assertFalse(production_settings["debug"])
        self.assertEqual(
            production_settings["database_engine"],
            "django.db.backends.postgresql",
        )
        self.assertEqual(production_settings["database_name"], "pms")
        self.assertTrue(production_settings["secure_redirect"])
        self.assertTrue(production_settings["session_cookie_secure"])
        self.assertTrue(production_settings["csrf_cookie_secure"])
        self.assertEqual(production_settings["hsts_seconds"], 31536000)
        self.assertEqual(
            production_settings["static_storage"],
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )

    def test_production_requires_database_url_instead_of_falling_back_to_sqlite(self):
        environment = os.environ.copy()
        environment.update(
            {
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "test-deployment-secret-with-adequate-length-0123456789",
            }
        )
        environment.pop("DATABASE_URL", None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from django.conf import settings; print(settings.DATABASES)",
            ],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "DATABASE_URL must be set when DEBUG is False.",
            result.stderr,
        )


class HealthCheckTests(TestCase):
    def test_health_check_reports_application_and_database_status(self):
        response = Client().get(reverse("health-check"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_check_reports_database_failure(self):
        with self.assertLogs(health.__name__, level="ERROR"):
            with patch(
                "config.health.connection.cursor",
                side_effect=OperationalError("offline"),
            ):
                response = Client().get(reverse("health-check"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})


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
