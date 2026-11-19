import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_GET, require_POST

from .forms import RegistrationForm
from .models import User
from .tokens import email_confirmation_token

logger = logging.getLogger(__name__)


class EmailLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.input_type = "email"
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not username:
            return username

        user_model = get_user_model()
        return (
            user_model.objects.filter(email__iexact=username)
            .values_list("email", flat=True)
            .first()
            or username
        )


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
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.is_active = False
                    user.save()
                    confirmation_path = reverse(
                        "email-confirm",
                        kwargs={
                            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                            "token": email_confirmation_token.make_token(user),
                        },
                    )
                    sent_count = send_mail(
                        subject="Confirm your Project Management System email",
                        message=(
                            f"Hello {user.full_name},\n\n"
                            "Confirm your email address to activate your account:\n"
                            f"{request.build_absolute_uri(confirmation_path)}\n\n"
                            "This link expires after 24 hours. If you did not create "
                            "this account, you can ignore this message."
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False,
                    )
                    if sent_count != 1:
                        raise RuntimeError("The registration confirmation email was not sent.")
            except (OSError, RuntimeError):
                # SMTP unreachable, refused or misconfigured. The transaction above has
                # rolled back, so no unconfirmed account is left behind.
                logger.exception("Registration confirmation email could not be sent.")
                form.add_error(
                    None,
                    "We couldn't send the confirmation email, so your account was not "
                    "created. Please try again later or ask an administrator to create "
                    "your account.",
                )
            else:
                messages.success(
                    request,
                    f"Check {user.email} for a link to confirm your email address.",
                )
                return redirect("login")
    else:
        form = RegistrationForm()

    return render(request, "registration/register.html", {"form": form})


def people_management(request):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_admin:
        raise PermissionDenied

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            employee = form.save()
            messages.success(
                request,
                f"Employee account created for {employee.full_name}. "
                "Share the initial password with them securely.",
            )
            return redirect("people-management")
    else:
        form = RegistrationForm()

    people = User.objects.order_by("full_name", "email")
    return render(
        request,
        "accounts/people_management.html",
        {"form": form, "people": people},
    )


@require_POST
def employee_toggle_active(request, user_id):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_admin:
        raise PermissionDenied

    employee = get_object_or_404(User, pk=user_id)
    if employee.is_admin:
        messages.error(
            request,
            "Administrator accounts cannot be deactivated from employee management.",
        )
        return redirect("people-management")

    employee.is_active = not employee.is_active
    employee.save(update_fields=["is_active"])
    status = "activated" if employee.is_active else "deactivated"
    messages.success(request, f"{employee.full_name} has been {status}.")
    return redirect("people-management")


@require_GET
def confirm_email(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id, is_active=False)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not email_confirmation_token.check_token(user, token):
        messages.error(request, "This email confirmation link is invalid or has expired.")
        return redirect("login")

    user.is_active = True
    user.save(update_fields=["is_active"])
    messages.success(request, "Your email address is confirmed. You can now log in.")
    return redirect("login")


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
