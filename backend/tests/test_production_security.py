from io import StringIO
from django.conf import global_settings, settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.core.management import call_command
from django.test import TestCase, override_settings

from config import settings as production_settings

User = get_user_model()


class ProductionSecurityTests(TestCase):
    def test_password_uses_pbkdf2_hasher(self):
        # The test suite swaps in a fast hasher (config/test_settings.py), so
        # check the hashers the real application settings would use.
        production_hashers = getattr(
            production_settings,
            "PASSWORD_HASHERS",
            global_settings.PASSWORD_HASHERS,
        )
        self.assertIn("PBKDF2", production_hashers[0])
        with override_settings(PASSWORD_HASHERS=production_hashers):
            user = User.objects.create_user(
                username="sec_user",
                email="sec@example.com",
                full_name="Security User",
                password="StrongPassword123!",
            )
            hasher = identify_hasher(user.password)
        self.assertIn("pbkdf2", hasher.algorithm.lower())
        self.assertNotIn("StrongPassword123!", user.password)

    def test_security_headers_configured(self):
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertTrue(settings.SECURE_BROWSER_XSS_FILTER)
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

    def test_verify_production_security_command(self):
        out = StringIO()
        call_command("verify_production_security", stdout=out)
        output = out.getvalue()
        self.assertIn("Running production security audit...", output)
        self.assertIn("CSRF middleware active.", output)
