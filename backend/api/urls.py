from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    path("projects/", views.project_list_api, name="project-list"),
    path("projects/<int:project_id>/", views.project_detail_api, name="project-detail"),
]
