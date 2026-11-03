from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone


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
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Comment by {self.author} on {self.task}"


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
