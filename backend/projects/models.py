from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.core.exceptions import ValidationError


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        ACTIVE = "ACTIVE", "Active"
        ON_HOLD = "ON_HOLD", "On Hold"
        COMPLETED = "COMPLETED", "Completed"
        ARCHIVED = "ARCHIVED", "Archived"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="owned_projects",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(start_date__isnull=True)
                    | Q(due_date__isnull=True)
                    | Q(due_date__gte=F("start_date"))
                ),
                name="project_due_date_after_start_date",
            )
        ]

    def __str__(self):
        return self.name


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        PROJECT_MANAGER = "PROJECT_MANAGER", "Project Manager"
        TEAM_MEMBER = "TEAM_MEMBER", "Team Member"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    project_role = models.CharField(max_length=30, choices=Role.choices)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["project_id", "user_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="unique_project_membership",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.project} ({self.get_project_role_display()})"


class Sprint(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="sprints"
    )
    name = models.CharField(max_length=200)
    goal = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_sprints",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="unique_project_sprint_name"
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="sprint_end_date_after_start_date",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["PLANNED", "ACTIVE", "COMPLETED"]),
                name="sprint_status_valid_choice",
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(status="ACTIVE"),
                name="unique_active_sprint_per_project",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"], name="sprint_project_status_idx"),
            models.Index(fields=["project", "start_date"], name="sprint_project_start_idx"),
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be earlier than the start date."})
        if self.pk:
            previous_status = (
                type(self).objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            allowed = {
                self.Status.PLANNED: {self.Status.PLANNED, self.Status.ACTIVE},
                self.Status.ACTIVE: {self.Status.ACTIVE, self.Status.COMPLETED},
                self.Status.COMPLETED: {self.Status.COMPLETED},
            }
            if previous_status and self.status not in allowed[previous_status]:
                raise ValidationError(
                    {"status": "Sprint lifecycle transitions must proceed forward."}
                )

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.project.name})"


class Milestone(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="milestones"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["target_date", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="unique_project_milestone_name"
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
                ),
                name="milestone_status_valid_choice",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "status"], name="milestone_project_status_idx"),
            models.Index(fields=["project", "target_date"], name="milestone_project_target_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.project.name})"


class SprintTaskHistory(models.Model):
    task = models.ForeignKey(
        "tasks.Task", on_delete=models.CASCADE, related_name="sprint_history"
    )
    sprint = models.ForeignKey(
        Sprint, on_delete=models.PROTECT, related_name="task_history"
    )
    carried_over_to = models.ForeignKey(
        Sprint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="carried_in_task_history",
    )
    carried_over = models.BooleanField(default=False)
    event_type = models.CharField(max_length=30, default="CARRY_OVER")
    carry_over_reason = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sprint_task_history_events",
    )
    carried_over_at = models.DateTimeField(null=True, blank=True)
    task_status = models.CharField(max_length=20)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(carried_over=False, carried_over_to__isnull=True)
                    | Q(carried_over=True, carried_over_to__isnull=False)
                ),
                name="sprint_history_carry_over_target",
            ),
        ]
        indexes = [
            models.Index(fields=["sprint", "recorded_at"], name="history_sprint_recorded_idx"),
            models.Index(fields=["task", "recorded_at"], name="history_task_recorded_idx"),
        ]

    def clean(self):
        super().clean()
        if self.carried_over and not self.carried_over_to_id:
            raise ValidationError({"carried_over_to": "A carry-over sprint is required."})
        if self.carried_over_to_id and self.carried_over_to_id == self.sprint_id:
            raise ValidationError({"carried_over_to": "A task cannot carry over to the same sprint."})

    def __str__(self):
        return f"{self.task} in {self.sprint}"
