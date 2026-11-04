import time
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = "Verify database connectivity, measure query latency, and check applied migrations."

    def handle(self, *args, **options):
        self.stdout.write("Testing database connection...")
        start_time = time.time()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            latency = round((time.time() - start_time) * 1000, 2)
            engine = connection.settings_dict.get("ENGINE", "unknown")
            db_name = connection.settings_dict.get("NAME", "unknown")

            recorder = MigrationRecorder(connection)
            applied_count = recorder.migration_qs.count()

            self.stdout.write(self.style.SUCCESS(
                f"[OK] Database connection successful!\n"
                f"     Engine: {engine}\n"
                f"     Database: {db_name}\n"
                f"     Latency: {latency} ms\n"
                f"     Applied Migrations: {applied_count}"
            ))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f"[ERROR] Database connection failed: {exc}\n"
                f"        Check environment variables DJANGO_DB_HOST, DJANGO_DB_PORT, and DJANGO_DB_PASSWORD."
            ))
            raise exc
