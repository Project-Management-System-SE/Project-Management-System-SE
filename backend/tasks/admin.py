from django.contrib import admin

from .notifications import notify_task_assignment, notify_task_status_change
from .models import Task, TaskLabel


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "status", "assignee", "priority", "due_date")
    list_filter = ("status", "priority", "project")
    search_fields = ("title", "description", "project__name", "assignee__email")

    def save_model(self, request, obj, form, change):
        previous = Task.objects.get(pk=obj.pk) if change else None
        super().save_model(request, obj, form, change)

        if previous is None:
            if obj.assignee_id:
                notify_task_assignment(obj)
            return

        if obj.assignee_id and obj.assignee_id != previous.assignee_id:
            notify_task_assignment(obj)
        if obj.status != previous.status:
            notify_task_status_change(obj, request.user)


@admin.register(TaskLabel)
class TaskLabelAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "created_at")
    list_filter = ("project",)
    search_fields = ("name", "project__name")
