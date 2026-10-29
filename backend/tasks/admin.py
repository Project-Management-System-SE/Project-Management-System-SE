from django.contrib import admin

from .models import Task, TaskLabel


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "status", "assignee", "priority", "due_date")
    list_filter = ("status", "priority", "project")
    search_fields = ("title", "description", "project__name", "assignee__email")


@admin.register(TaskLabel)
class TaskLabelAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "created_at")
    list_filter = ("project",)
    search_fields = ("name", "project__name")
