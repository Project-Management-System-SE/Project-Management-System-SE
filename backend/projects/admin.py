from django.contrib import admin

from .models import Project, ProjectMembership


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
