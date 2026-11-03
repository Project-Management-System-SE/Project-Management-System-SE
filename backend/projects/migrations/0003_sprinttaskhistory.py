import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0002_sprint_milestone"),
        ("tasks", "0006_task_milestone_task_sprint_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SprintTaskHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("carried_over", models.BooleanField(default=False)),
                ("carry_over_reason", models.TextField(blank=True)),
                ("carried_over_at", models.DateTimeField(blank=True, null=True)),
                ("task_status", models.CharField(max_length=20)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "carried_over_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="carried_in_task_history",
                        to="projects.sprint",
                    ),
                ),
                (
                    "sprint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="task_history",
                        to="projects.sprint",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sprint_history",
                        to="tasks.task",
                    ),
                ),
            ],
            options={"ordering": ["-recorded_at", "-pk"]},
        ),
        migrations.AddIndex(
            model_name="sprinttaskhistory",
            index=models.Index(
                fields=["sprint", "recorded_at"],
                name="history_sprint_recorded_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="sprinttaskhistory",
            index=models.Index(
                fields=["task", "recorded_at"],
                name="history_task_recorded_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="sprinttaskhistory",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("carried_over", False),
                        ("carried_over_to__isnull", True),
                    ),
                    models.Q(
                        ("carried_over", True),
                        ("carried_over_to__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="sprint_history_carry_over_target",
            ),
        ),
    ]
