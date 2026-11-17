import json
import os
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Create a compressed database fixture and uploaded-media backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=None,
            help="Directory for the backup archive (defaults to DJANGO_BACKUP_DIR or backend/backups).",
        )

    def handle(self, *args, **options):
        output_dir = Path(
            options["output_dir"]
            or os.environ.get(
                "DJANGO_BACKUP_DIR",
                str(settings.BASE_DIR / "backups"),
            )
        ).expanduser()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise CommandError(f"Could not create backup directory: {error}") from error
        if not output_dir.is_dir():
            raise CommandError(f"Backup destination is not a directory: {output_dir}")

        created_at = timezone.now()
        backup_path = output_dir / (
            f"pms-backup-{created_at.strftime('%Y%m%dT%H%M%S.%fZ')}.zip"
        )
        fixture_path = None
        temporary_archive_path = None
        media_root = Path(settings.MEDIA_ROOT)
        media_files = []
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                dir=output_dir,
                delete=False,
            ) as fixture:
                fixture_path = Path(fixture.name)
                with transaction.atomic():
                    call_command(
                        "dumpdata",
                        format="json",
                        indent=2,
                        natural_foreign=True,
                        natural_primary=True,
                        stdout=fixture,
                    )

            with tempfile.NamedTemporaryFile(
                suffix=".tmp",
                dir=output_dir,
                delete=False,
            ) as archive_file:
                temporary_archive_path = Path(archive_file.name)

            with zipfile.ZipFile(
                temporary_archive_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                archive.write(fixture_path, arcname="database.json")
                if media_root.is_dir():
                    for media_file in media_root.rglob("*"):
                        if media_file.is_file() and not media_file.is_symlink():
                            archive.write(
                                media_file,
                                arcname=f"media/{media_file.relative_to(media_root).as_posix()}",
                            )
                            media_files.append(media_file)
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "format": "django-fixture-and-media-v1",
                            "created_at": created_at.isoformat(),
                            "database_vendor": connection.vendor,
                            "media_file_count": len(media_files),
                        },
                        indent=2,
                    ),
                )
            os.replace(temporary_archive_path, backup_path)
        except OSError as error:
            raise CommandError(f"Could not create database backup: {error}") from error
        finally:
            for temporary_path in (fixture_path, temporary_archive_path):
                if temporary_path and temporary_path.exists():
                    temporary_path.unlink()

        self.stdout.write(
            self.style.SUCCESS(
                f"Created backup {backup_path} with {len(media_files)} media file(s)."
            )
        )
