from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    list_display = (
        "username",
        "email",
        "full_name",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    search_fields = ("username", "email", "full_name")
    ordering = ("username",)
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Profile", {"fields": ("full_name",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "full_name", "password1", "password2"),
            },
        ),
    )
