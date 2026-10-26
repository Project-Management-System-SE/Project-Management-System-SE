from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class UserAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="safe-password-123",
        )
        self.client.force_login(self.admin_user)

    def test_add_user_page_includes_custom_required_fields(self):
        response = self.client.get(reverse("admin:accounts_user_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="full_name"')
