from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    path("projects/", views.project_list_api, name="project-list"),
    path("projects/<int:project_id>/", views.project_detail_api, name="project-detail"),
    path("projects/<int:project_id>/tasks/", views.task_list_create_api, name="project-tasks"),
    path("tasks/<int:task_id>/", views.task_detail_api, name="task-detail"),
    path("tasks/<int:task_id>/status/", views.task_status_api, name="task-status"),
]
