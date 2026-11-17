from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone


class WorkflowState(models.Model):
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="workflow_states",
    )
    key = models.CharField(max_length=20)
    name = models.CharField(max_length=50)
    position = models.PositiveSmallIntegerField()
    is_initial = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "key"],
                name="unique_project_workflow_state_key",
            ),
            models.UniqueConstraint(
                fields=["project", "name"],
                name="unique_project_workflow_state_name",
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=models.Q(is_initial=True),
                name="unique_project_initial_workflow_state",
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=models.Q(is_final=True),
                name="unique_project_final_workflow_state",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.project.name})"


class WorkflowTransition(models.Model):
    from_state = models.ForeignKey(
        WorkflowState,
        on_delete=models.CASCADE,
        related_name="outgoing_transitions",
    )
    to_state = models.ForeignKey(
        WorkflowState,
        on_delete=models.CASCADE,
        related_name="incoming_transitions",
    )

    class Meta:
        ordering = ["from_state__position", "to_state__position"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_state", "to_state"],
                name="unique_workflow_state_transition",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.from_state_id
            and self.to_state_id
            and self.from_state.project_id != self.to_state.project_id
        ):
            raise ValidationError("Workflow transitions must stay within one project.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.from_state.name} -> {self.to_state.name}"


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
        BACKLOG = "BACKLOG", "Backlog"
        TODO = "TODO", "To Do"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        REVIEW = "REVIEW", "Review"
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
    workflow_state = models.ForeignKey(
        WorkflowState,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
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
                condition=models.Q(
                    status__in=["BACKLOG", "TODO", "IN_PROGRESS", "REVIEW", "DONE"]
                ),
                name="task_status_valid_choice",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    priority__in=["LOW", "MEDIUM", "HIGH", "CRITICAL"]
                ),
                name="task_priority_valid_choice",
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
        if (
            self.project_id
            and WorkflowState.objects.filter(project_id=self.project_id).exists()
            and not self.workflow_state_id
        ):
            raise ValidationError(
                {"workflow_state": "Choose a state from this project's workflow."}
            )
        if (
            self.workflow_state_id
            and self.workflow_state.project_id != self.project_id
        ):
            raise ValidationError(
                {"workflow_state": "The workflow state must belong to this task's project."}
            )
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
        if self.project_id and not self.workflow_state_id:
            self.workflow_state = WorkflowState.objects.filter(
                project_id=self.project_id,
                key=self.status,
            ).first()
            if (
                self.workflow_state is None
                and self.status in {self.Status.BACKLOG, self.Status.TODO}
            ):
                self.workflow_state = WorkflowState.objects.filter(
                    project_id=self.project_id,
                    is_initial=True,
                ).first()

        if self.workflow_state_id:
            from .workflow import task_status_for_workflow_state

            self.status = task_status_for_workflow_state(self.workflow_state)

        is_complete = (
            self.workflow_state.is_final
            if self.workflow_state_id
            else self.status == self.Status.DONE
        )
        completion_changed = False
        if is_complete and not self.completed_at:
            self.completed_at = timezone.now()
            completion_changed = True
        elif not is_complete and self.completed_at:
            self.completed_at = None
            completion_changed = True

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if self.workflow_state_id:
                update_fields.add("workflow_state")
            if completion_changed:
                update_fields.add("completed_at")
            kwargs["update_fields"] = update_fields

        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)

    def get_labels_as_string(self):
        return ", ".join(self.labels.values_list("name", flat=True))

    def get_status_display(self):
        if self.workflow_state_id:
            return self.workflow_state.name
        return dict(self.Status.choices).get(self.status, self.status)

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
