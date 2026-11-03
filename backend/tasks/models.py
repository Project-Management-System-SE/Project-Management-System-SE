import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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
    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        TODO = "TODO", "To Do"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        DONE = "DONE", "Done"

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
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

    def save(self, *args, **kwargs):
        if self.title:
            self.title = self.title.strip()
        from django.utils import timezone

        if self.status == self.Status.DONE and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != self.Status.DONE and self.completed_at:
            self.completed_at = None
        super().save(*args, **kwargs)

    def get_labels_as_string(self):
        return ", ".join(self.labels.values_list("name", flat=True))

    def __str__(self):
        return f"{self.title} ({self.project.name})"


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
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
