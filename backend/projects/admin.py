from django.contrib import admin

from .models import Milestone, Project, ProjectMembership, Sprint, SprintTaskHistory


class ProjectMembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "start_date", "due_date", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "description", "owner__username", "owner__email")
    inlines = [ProjectMembershipInline]


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "project_role", "joined_at")
    list_filter = ("project_role",)
    search_fields = ("project__name", "user__username", "user__email")


@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "status", "start_date", "end_date", "created_by")
    list_filter = ("status", "project")
    search_fields = ("name", "goal", "project__name")


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "status", "target_date")
    list_filter = ("status", "project")
    search_fields = ("name", "description", "project__name")


@admin.register(SprintTaskHistory)
class SprintTaskHistoryAdmin(admin.ModelAdmin):
    list_display = ("task", "sprint", "carried_over_to", "event_type", "actor", "recorded_at")
    list_filter = ("event_type", "sprint")
    search_fields = ("task__title", "sprint__name")
    readonly_fields = ("recorded_at",)
