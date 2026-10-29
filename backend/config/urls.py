from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from accounts import views as account_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/register/", account_views.register, name="register"),
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
