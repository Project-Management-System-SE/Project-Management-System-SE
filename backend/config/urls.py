from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from accounts import views as account_views
from config.health import health_check
from tasks import api as task_api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path("accounts/login/", account_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/register/", account_views.register, name="register"),
    path("people/", account_views.people_management, name="people-management"),
    path(
        "people/<int:user_id>/toggle-active/",
        account_views.employee_toggle_active,
        name="employee-toggle-active",
    ),
    path("api/v1/projects/", task_api.api_project_list, name="api-project-list"),
    path(
        "api/v1/projects/<int:project_id>/",
        task_api.api_project_detail,
        name="api-project-detail",
    ),
    path(
        "api/v1/projects/<int:project_id>/tasks/",
        task_api.api_project_task_list,
        name="api-project-task-list",
    ),
    path(
        "api/v1/projects/<int:project_id>/tasks/<int:task_id>/",
        task_api.api_project_task_detail,
        name="api-project-task-detail",
    ),
    path(
        "accounts/confirm/<uidb64>/<token>/",
        account_views.confirm_email,
        name="email-confirm",
    ),
    path(
        "accounts/password-reset/",
        account_views.PasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        account_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        account_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        account_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("", include("projects.urls")),
    path("", include("tasks.urls")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
