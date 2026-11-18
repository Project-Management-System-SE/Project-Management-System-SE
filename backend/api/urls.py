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
    path("projects/<int:project_id>/sprints/", views.sprint_list_api, name="project-sprints"),
    path("projects/<int:project_id>/milestones/", views.milestone_list_api, name="project-milestones"),
    path("openapi.json", openapi_spec_api, name="openapi-spec"),
    path("docs/", api_docs_viewer, name="api-docs"),
]
