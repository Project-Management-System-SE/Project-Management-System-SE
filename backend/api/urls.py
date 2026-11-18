from .docs import openapi_spec_api, api_docs_viewer
from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    path("projects/", views.project_list_api, name="project-list"),
    path("projects/<int:project_id>/", views.project_detail_api, name="project-detail"),
    path("projects/<int:project_id>/members/", views.project_membership_api, name="project-members"),
    path(
        "projects/<int:project_id>/members/<int:membership_id>/",
        views.project_membership_detail_api,
        name="project-member-detail",
    ),
    path("projects/<int:project_id>/tasks/", views.task_list_create_api, name="project-tasks"),
    path("tasks/<int:task_id>/", views.task_detail_api, name="task-detail"),
    path("tasks/<int:task_id>/status/", views.task_status_api, name="task-status"),
    path("projects/<int:project_id>/workflow/", views.project_workflow_api, name="project-workflow"),
    path("projects/<int:project_id>/workflow/configure/", views.project_workflow_update_api, name="project-workflow-update"),
    path("projects/<int:project_id>/sprints/", views.sprint_list_api, name="project-sprints"),
    path("projects/<int:project_id>/sprints/<int:sprint_id>/", views.sprint_detail_api, name="project-sprint-detail"),
    path("projects/<int:project_id>/milestones/", views.milestone_list_api, name="project-milestones"),
    path("projects/<int:project_id>/milestones/<int:milestone_id>/", views.milestone_detail_api, name="project-milestone-detail"),
    path("projects/<int:project_id>/tasks/<int:task_id>/comments/", views.task_comment_api, name="task-comments"),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/comments/<int:comment_id>/",
        views.task_comment_detail_api,
        name="task-comment-detail",
    ),
    path("projects/<int:project_id>/reports/", views.project_report_api, name="project-reports"),
    path("openapi.json", openapi_spec_api, name="openapi-spec"),
    path("docs/", api_docs_viewer, name="api-docs"),
]
