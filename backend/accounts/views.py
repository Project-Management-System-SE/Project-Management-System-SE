from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import RegistrationForm


class EmailLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.input_type = "email"
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"


class LoginView(auth_views.LoginView):
    authentication_form = EmailLoginForm

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(60 * 60 * 24 * 30)
        return response


def register(request):
    if request.user.is_authenticated:
        return redirect("projects:dashboard")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                sent_count = send_mail(
                    subject="Welcome to Project Management System",
                    message=(
                        f"Hello {user.full_name},\n\n"
                        "Your Project Management System account has been created "
                        "successfully with this email address. You can now log in "
                        "using your email address and password.\n\n"
                        "If you did not create this account, please contact your "
                        "system administrator."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                if sent_count != 1:
                    raise RuntimeError("The registration confirmation email was not sent.")

            messages.success(
                request,
                f"Your account has been created. A confirmation email was sent to {user.email}.",
            )
            return redirect("login")
    else:
        form = RegistrationForm()

    return render(request, "registration/register.html", {"form": form})


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"
