from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "status", "assignee", "priority", "due_date")
    list_filter = ("status", "priority", "project")
    search_fields = ("title", "description", "project__name", "assignee__email")
