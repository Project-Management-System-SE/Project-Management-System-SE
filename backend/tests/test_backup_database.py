import json
import tempfile
import zipfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import User
from projects.models import Project
from tasks.models import Task


class BackupDatabaseCommandTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="test-pass-123",
        )
        project = Project.objects.create(name="Backup project", owner=owner)
        Task.objects.create(
            project=project,
            title="Backed up task",
            created_by=owner,
        )

    def test_backup_contains_database_fixture_manifest_and_uploaded_media(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            media_root = temporary_path / "media"
            output_dir = temporary_path / "backups"
            upload = media_root / "tasks" / "attachment.txt"
            upload.parent.mkdir(parents=True)
            upload.write_text("test attachment", encoding="utf-8")
            with override_settings(MEDIA_ROOT=media_root):
                call_command("backup_database", output_dir=str(output_dir))

            archives = list(output_dir.glob("pms-backup-*.zip"))
            self.assertEqual(len(archives), 1)
            with zipfile.ZipFile(archives[0]) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"database.json", "manifest.json", "media/tasks/attachment.txt"},
                )
                fixture = json.loads(archive.read("database.json"))
                manifest = json.loads(archive.read("manifest.json"))

            backed_up_task = next(
                item
                for item in fixture
                if item["model"] == "tasks.task"
                and item["fields"]["title"] == "Backed up task"
            )
            self.assertTrue(backed_up_task["pk"])
            self.assertEqual(manifest["media_file_count"], 1)
            self.assertEqual(manifest["database_vendor"], "sqlite")
