from io import StringIO
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.core.management import call_command
from django.test import TestCase

User = get_user_model()


class ProductionSecurityTests(TestCase):
    def test_password_uses_pbkdf2_hasher(self):
        user = User.objects.create_user(
            username="sec_user",
            email="sec@example.com",
            full_name="Security User",
            password="StrongPassword123!",
        )
        hasher = identify_hasher(user.password)
        self.assertIn("pbkdf2", hasher.algorithm.lower())

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
