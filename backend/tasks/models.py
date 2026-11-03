import csv
import io
import struct
import uuid
import zipfile
import zlib
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone


def _is_valid_png(content):
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return False

    offset = 8
    has_header = False
    has_image_data = False
    while offset + 12 <= len(content):
        chunk_size = struct.unpack(">I", content[offset : offset + 4])[0]
        chunk_type = content[offset + 4 : offset + 8]
        chunk_end = offset + 12 + chunk_size
        if chunk_end > len(content):
            return False

        chunk_data = content[offset + 8 : offset + 8 + chunk_size]
        expected_crc = struct.unpack(">I", content[offset + 8 + chunk_size : chunk_end])[0]
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return False

        if not has_header:
            if chunk_type != b"IHDR" or chunk_size != 13:
                return False
            width, height = struct.unpack(">II", chunk_data[:8])
            if width == 0 or height == 0:
                return False
            has_header = True
        elif chunk_type == b"IHDR":
            return False

        if chunk_type == b"IDAT":
            has_image_data = True
        if chunk_type == b"IEND":
            return chunk_size == 0 and has_header and has_image_data and chunk_end == len(content)

        offset = chunk_end

    return False


def _is_valid_office_zip(extension, content):
    required_parts = {
        "docx": {"[Content_Types].xml", "word/document.xml"},
        "xlsx": {"[Content_Types].xml", "xl/workbook.xml"},
    }[extension]
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return required_parts.issubset(archive.namelist())
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def _attachment_content_matches(extension, content):
    if extension in {"txt", "csv"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return False
        if any(ord(character) < 32 and character not in "\t\n\r\f" for character in text):
            return False
        if extension == "csv":
            try:
                for _ in csv.reader(io.StringIO(text, newline=""), strict=True):
                    pass
            except csv.Error:
                return False
        return True

    if extension == "pdf":
        return content.startswith(b"%PDF-") and b"%%EOF" in content[-1024:]
    if extension == "png":
        return _is_valid_png(content)
    if extension in {"jpg", "jpeg"}:
        return content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")
    if extension == "gif":
        return (
            content.startswith((b"GIF87a", b"GIF89a"))
            and len(content) >= 14
            and struct.unpack("<HH", content[6:10]) != (0, 0)
            and content.endswith(b";")
        )
    if extension in {"doc", "xls"}:
        return (
            content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            and len(content) >= 512
            and content[28:30] in {b"\xfe\xff", b"\xff\xfe"}
            and struct.unpack("<H", content[30:32])[0] in {9, 12}
        )
    if extension in {"docx", "xlsx"}:
        return _is_valid_office_zip(extension, content)
    return False


def validate_task_attachment(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower().lstrip(".")
    allowed_extensions = settings.TASK_ATTACHMENT_ALLOWED_EXTENSIONS
    if extension not in allowed_extensions:
        allowed_types = ", ".join(f".{item}" for item in allowed_extensions)
        raise ValidationError(
            f"Unsupported file type. Allowed file types: {allowed_types}."
        )

    max_size = settings.TASK_ATTACHMENT_MAX_SIZE_BYTES
    if uploaded_file.size > max_size:
        raise ValidationError(
            f"File must be no larger than {task_attachment_max_size_label()}."
        )
    if uploaded_file.size == 0:
        raise ValidationError("The uploaded file is empty.")

    try:
        content = uploaded_file.read(max_size + 1)
        if len(content) > max_size:
            raise ValidationError(
                f"File must be no larger than {task_attachment_max_size_label()}."
            )
        if not content:
            raise ValidationError("The uploaded file is empty.")
        if not _attachment_content_matches(extension, content):
            raise ValidationError(
                f"The file contents do not match the .{extension} file type. "
                f"Please choose a valid .{extension} file."
            )
    except (OSError, EOFError, ValueError):
        raise ValidationError("The uploaded file could not be read.") from None
    finally:
        uploaded_file.seek(0)


def task_attachment_max_size_label():
    max_size = settings.TASK_ATTACHMENT_MAX_SIZE_BYTES
    if max_size % (1024 * 1024) == 0:
        return f"{max_size // (1024 * 1024)} MB"
    if max_size % 1024 == 0:
        return f"{max_size // 1024} KB"
    return f"{max_size} bytes"


def task_attachment_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"tasks/{instance.task_id}/{uuid.uuid4().hex}{extension}"


class TaskLabel(models.Model):
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="labels",
    )
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                name="unique_project_task_label",
            )
        ]

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip().lower()

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "TODO", "To Do"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        DONE = "DONE", "Done"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    sprint = models.ForeignKey(
        "projects.Sprint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    milestone = models.ForeignKey(
        "projects.Milestone",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
    )
    estimated_effort = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    actual_effort = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    due_date = models.DateField(null=True, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_tasks",
    )
    labels = models.ManyToManyField(
        TaskLabel,
        blank=True,
        related_name="tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["TODO", "IN_PROGRESS", "DONE"]),
                name="task_status_valid_choice",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    priority__in=["LOW", "MEDIUM", "HIGH", "CRITICAL"]
                ),
                name="task_priority_valid_choice",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(estimated_effort__isnull=True)
                    | models.Q(estimated_effort__gte=0)
                ),
                name="task_estimated_effort_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(actual_effort__isnull=True)
                    | models.Q(actual_effort__gte=0)
                ),
                name="task_actual_effort_non_negative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["project", "status"],
                name="task_project_status_idx",
            ),
            models.Index(
                fields=["project", "-created_at"],
                name="task_project_created_idx",
            ),
            models.Index(
                fields=["project", "sprint", "status"],
                name="task_project_sprint_status_idx",
            ),
            models.Index(
                fields=["project", "milestone"],
                name="task_project_milestone_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.title:
            self.title = self.title.strip()
        if self.assignee_id and self.project_id:
            is_member = (
                self.project.memberships.filter(user_id=self.assignee_id).exists()
                or self.project.owner_id == self.assignee_id
            )
            if not is_member:
                raise ValidationError(
                    {"assignee": "The assignee must be an authorized member of the project."}
                )
        if self.sprint_id and self.project_id and self.sprint.project_id != self.project_id:
            raise ValidationError({"sprint": "The sprint must belong to the task's project."})
        if self.milestone_id and self.project_id and self.milestone.project_id != self.project_id:
            raise ValidationError(
                {"milestone": "The milestone must belong to the task's project."}
            )

    def save(self, *args, **kwargs):
        if self.title:
            self.title = self.title.strip()
        completion_changed = False
        if self.status == self.Status.DONE and not self.completed_at:
            self.completed_at = timezone.now()
            completion_changed = True
        elif self.status != self.Status.DONE and self.completed_at:
            self.completed_at = None
            completion_changed = True

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if completion_changed:
                update_fields.add("completed_at")
            kwargs["update_fields"] = update_fields

        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)

    def get_labels_as_string(self):
        return ", ".join(self.labels.values_list("name", flat=True))

    def __str__(self):
        return f"{self.title} ({self.project.name})"


class TaskComment(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="task_comments",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Comment by {self.author} on {self.task}"


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="task_attachments",
    )
    file = models.FileField(
        upload_to=task_attachment_upload_path,
        validators=[validate_task_attachment],
    )
    original_filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.original_filename} attached to {self.task}"


class TaskDueReminder(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="due_reminders",
    )
    due_date = models.DateField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "due_date"],
                name="unique_task_due_date_reminder",
            )
        ]

    def __str__(self):
        return f"Due reminder for {self.task} on {self.due_date}"


class UserNotification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    @property
    def is_read(self):
        return self.read_at is not None

    def __str__(self):
        return f"{self.title} for {self.recipient}"


@receiver(m2m_changed, sender=Task.labels.through)
def validate_task_label_project(sender, instance, action, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return

    if isinstance(instance, Task):
        mismatched_labels = TaskLabel.objects.filter(
            pk__in=pk_set
        ).exclude(project_id=instance.project_id)
        if mismatched_labels.exists():
            raise ValidationError(
                "A task can only be associated with labels from its project."
            )
    elif isinstance(instance, TaskLabel):
        mismatched_tasks = Task.objects.filter(
            pk__in=pk_set
        ).exclude(project_id=instance.project_id)
        if mismatched_tasks.exists():
            raise ValidationError(
                "A task can only be associated with labels from its project."
            )
