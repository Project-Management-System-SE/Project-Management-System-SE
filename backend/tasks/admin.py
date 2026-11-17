from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .notifications import notify_task_assignment, notify_task_status_change
from .audit import changes_from_form, record_audit
from .models import AuditLog, Task, TaskLabel


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "status", "assignee", "priority", "due_date")
    list_filter = ("status", "priority", "project")
    search_fields = ("title", "description", "project__name", "assignee__email")

    def save_model(self, request, obj, form, change):
        previous = Task.objects.get(pk=obj.pk) if change else None
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if previous is None:
                record_audit(request.user, AuditLog.Action.CREATE, obj)
            else:
                changes = changes_from_form(form)
                if changes:
                    record_audit(
                        request.user,
                        AuditLog.Action.UPDATE,
                        obj,
                        changes=changes,
                    )
        if previous is None:
            if obj.assignee_id:
                notify_task_assignment(obj)
            return

        if obj.assignee_id and obj.assignee_id != previous.assignee_id:
            notify_task_assignment(obj)
        if obj.status != previous.status:
            notify_task_status_change(obj, request.user)

    def delete_model(self, request, obj):
        with transaction.atomic():
            record_audit(request.user, AuditLog.Action.DELETE, obj)
            super().delete_model(request, obj)


@admin.register(TaskLabel)
class TaskLabelAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "created_at")
    list_filter = ("project",)
    search_fields = ("name", "project__name")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "action",
        "object_type",
        "object_name",
        "actor_name",
        "project_name",
    )
    list_filter = ("action", "object_type")
    search_fields = ("object_name", "project_name", "actor_name", "description")
    readonly_fields = [field.name for field in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Audit entries cannot be deleted.")
