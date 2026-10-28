from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard-alias"),
    path("projects/", views.project_list, name="project-list"),
    path("projects/new/", views.project_create, name="project-create"),
    path("projects/<int:project_id>/", views.project_detail, name="project-detail"),
    path(
        "projects/<int:project_id>/edit/",
        views.project_update,
        name="project-update",
    ),
    path(
        "projects/<int:project_id>/members/add/",
        views.project_add_member,
        name="project-add-member",
    ),
    path(
        "projects/<int:project_id>/members/<int:membership_id>/remove/",
        views.project_remove_member,
        name="project-remove-member",
    ),
    path(
        "projects/<int:project_id>/archive/",
        views.project_archive,
        name="project-archive",
    ),
    path(
        "projects/<int:project_id>/delete/",
        views.project_delete,
        name="project-delete",
    ),
]
