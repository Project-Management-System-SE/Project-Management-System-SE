from io import StringIO
from django.core.management import call_command
from django.test import TestCase


class DatabaseConfigTests(TestCase):
    def test_database_connection_command(self):
        out = StringIO()
        call_command("check_db_connection", stdout=out)
        output = out.getvalue()
        self.assertIn("Database connection successful!", output)
        self.assertIn("Applied Migrations:", output)
