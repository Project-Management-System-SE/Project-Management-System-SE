from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("my-tasks/", views.my_tasks, name="my-tasks"),
    path("notifications/", views.notification_inbox, name="notification-inbox"),
    path(
        "notifications/<int:notification_id>/read/",
        views.notification_mark_read,
        name="notification-mark-read",
    ),
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
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/comments/",
        views.task_comment_create,
        name="task-comment-create",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/comments/",
        views.task_add_comment,
        name="task-add-comment",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/attachments/",
        views.task_attachment_upload,
        name="task-attachment-upload",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/attachments/<int:attachment_id>/download/",
        views.task_attachment_download,
        name="task-attachment-download",
    ),
]
