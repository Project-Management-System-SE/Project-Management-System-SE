from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("tasks/", views.all_task_list, name="all-task-list"),
    path(
        "projects/<int:project_id>/tasks/",
        views.task_list,
        name="task-list",
    ),
    path(
        "projects/<int:project_id>/tasks/",
        views.task_list,
        name="project-task-list",
    ),
    path(
        "projects/<int:project_id>/tasks/new/",
        views.task_create,
        name="task-create",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/",
        views.task_detail,
        name="task-detail",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/edit/",
        views.task_update,
        name="task-update",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/status/",
        views.task_update_status,
        name="task-update-status",
    ),
]
