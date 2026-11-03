from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from config.notifications import create_notifications
from tasks.models import Task, TaskDueReminder


class Command(BaseCommand):
    help = "Create in-app reminders for assignees one day before task due dates."

    def handle(self, *args, **options):
        reminder_date = timezone.localdate() + timedelta(days=1)
        tasks = (
            Task.objects.filter(due_date=reminder_date, assignee__isnull=False)
            .exclude(status=Task.Status.DONE)
            .select_related("project", "assignee")
            .order_by("pk")
        )
        sent_count = 0

        for task in tasks:
            with transaction.atomic():
                _, created = TaskDueReminder.objects.get_or_create(
                    task=task,
                    due_date=reminder_date,
                )
                if not created:
                    continue

                create_notifications(
                    title=f"Task due tomorrow: {task.title}",
                    message=(
                        f"Your task '{task.title}' in project '{task.project.name}' "
                        f"is due tomorrow ({task.due_date:%Y-%m-%d})."
                    ),
                    recipients=[task.assignee],
                )
                sent_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {sent_count} task due-date notification(s) for {reminder_date}."
            )
        )
