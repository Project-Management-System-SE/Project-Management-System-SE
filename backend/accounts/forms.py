from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .models import User


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("full_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        local_part = user.email.partition("@")[0]
        base_username = slugify(local_part)[:140] or "user"
        username = base_username
        suffix = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username[:140 - len(str(suffix))]}{suffix}"
            suffix += 1

        user.username = username
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
            self.save_m2m()
        return user


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "full_name")


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"
