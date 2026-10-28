import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.forms import RegistrationForm
from accounts.models import User


class RegistrationFormTests(TestCase):
    def test_registration_requires_name_email_and_valid_matching_passwords(self):
        form = RegistrationForm(
            data={
                "full_name": "",
                "email": "not-an-email",
                "password1": "short",
                "password2": "different",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("full_name", form.errors)
        self.assertIn("email", form.errors)
        self.assertIn("password2", form.errors)

    def test_registration_rejects_case_insensitive_duplicate_email(self):
        User.objects.create_user(
            email="person@example.com",
            username="existing-person",
            full_name="Existing Person",
            password="existing-password-123",
        )
        form = RegistrationForm(
            data={
                "full_name": "New Person",
                "email": "PERSON@EXAMPLE.COM",
                "password1": "new-safe-password-123!",
                "password2": "new-safe-password-123!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class RegistrationViewTests(TestCase):
    def test_registration_creates_a_non_privileged_account(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "New Member",
                "email": "New.Member@example.com",
                "password1": "new-safe-password-123!",
                "password2": "new-safe-password-123!",
                "is_staff": "on",
                "is_superuser": "on",
            },
        )

        self.assertRedirects(response, reverse("login"))
        user = User.objects.get(email="new.member@example.com")
        self.assertEqual(user.full_name, "New Member")
        self.assertTrue(user.username)
        self.assertTrue(user.check_password("new-safe-password-123!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_admin)
        self.assertFalse(user.groups.exists())

    def test_registration_page_renders_required_fields_and_links_from_login(self):
        registration_response = self.client.get(reverse("register"))
        login_response = self.client.get(reverse("login"))

        self.assertEqual(registration_response.status_code, 200)
        self.assertContains(registration_response, 'name="full_name"')
        self.assertContains(registration_response, 'name="email"')
        self.assertContains(registration_response, 'name="password1"')
        self.assertNotContains(registration_response, 'name="username"')
        self.assertContains(login_response, reverse("register"))
        self.assertContains(login_response, reverse("password_reset"))

    def test_invalid_registration_does_not_create_an_account(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "",
                "email": "invalid-email",
                "password1": "short",
                "password2": "not-the-same",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetViewTests(TestCase):
    def setUp(self):
        self.email = "member@example.com"
        self.old_password = "current-safe-password-123"
        self.user = User.objects.create_user(
            email=self.email,
            username="member",
            full_name="Project Member",
            password=self.old_password,
        )

    def test_password_reset_link_expiry_is_one_day(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 60 * 60 * 24)

    def request_reset_link(self):
        response = self.client.post(
            reverse("password_reset"),
            {"email": self.email},
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.email, mail.outbox[0].to)
        link = re.search(r"https?://\S+", mail.outbox[0].body)
        self.assertIsNotNone(link)
        return urlsplit(link.group()).path

    def test_unknown_email_gets_same_confirmation_without_sending_email(self):
        known_response = self.client.post(
            reverse("password_reset"),
            {"email": self.email},
        )
        unknown_response = self.client.post(
            reverse("password_reset"),
            {"email": "unknown@example.com"},
        )

        self.assertEqual(known_response.status_code, 302)
        self.assertEqual(unknown_response.status_code, 302)
        self.assertEqual(known_response.url, unknown_response.url)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_changes_password_and_invalidates_old_link(self):
        reset_path = self.request_reset_link()

        response = self.client.get(reset_path)
        self.assertEqual(response.status_code, 302)
        confirm_path = response.url

        response = self.client.post(
            confirm_path,
            {
                "new_password1": "brand-new-safe-password-829!",
                "new_password2": "brand-new-safe-password-829!",
            },
        )
        self.assertRedirects(response, reverse("password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-safe-password-829!"))
        self.assertFalse(self.user.check_password(self.old_password))
        self.assertEqual(
            self.client.get(reset_path).context["validlink"],
            False,
        )

        login_response = self.client.post(
            reverse("login"),
            {"username": self.email, "password": self.old_password},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

        login_response = self.client.post(
            reverse("login"),
            {"username": self.email, "password": "brand-new-safe-password-829!"},
        )
        self.assertRedirects(login_response, reverse("projects:dashboard"))

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_password_reset_link_is_rejected(self):
        reset_path = self.request_reset_link()

        response = self.client.get(reset_path)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["validlink"])
        self.assertContains(response, "invalid or has expired")
