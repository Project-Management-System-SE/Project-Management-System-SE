from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Audit and verify production security configuration and deployment safeguards."

    def handle(self, *args, **options):
        self.stdout.write("Running production security audit...")
        issues = []

        if settings.DEBUG:
            issues.append("[WARN] DEBUG is True! In production, DJANGO_DEBUG must be 0/False.")
        else:
            self.stdout.write(self.style.SUCCESS("[PASS] DEBUG is False."))

        if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
            issues.append("[FAIL] SECRET_KEY is too short or missing.")
        else:
            self.stdout.write(self.style.SUCCESS("[PASS] SECRET_KEY meets complexity requirements."))

        if getattr(settings, "X_FRAME_OPTIONS", None) == "DENY":
            self.stdout.write(self.style.SUCCESS("[PASS] Clickjacking defense: X_FRAME_OPTIONS is DENY."))
        else:
            issues.append("[WARN] X_FRAME_OPTIONS is not DENY.")

        if getattr(settings, "CSRF_COOKIE_HTTPONLY", False):
            self.stdout.write(self.style.SUCCESS("[PASS] CSRF_COOKIE_HTTPONLY is enabled."))

        if getattr(settings, "SESSION_COOKIE_HTTPONLY", False):
            self.stdout.write(self.style.SUCCESS("[PASS] SESSION_COOKIE_HTTPONLY is enabled."))

        has_csrf_mw = "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
        if has_csrf_mw:
            self.stdout.write(self.style.SUCCESS("[PASS] CSRF middleware active."))
        else:
            issues.append("[FAIL] CSRF middleware is missing!")

        if issues:
            self.stdout.write("\nSecurity Warnings / Action Items:")
            for issue in issues:
                self.stdout.write(self.style.WARNING(f" - {issue}"))
        else:
            self.stdout.write(self.style.SUCCESS("\n[ALL CHECKS PASSED] Production security criteria satisfied."))
