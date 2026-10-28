from django import forms

from accounts.models import User

from .models import Project, ProjectMembership


class ProjectForm(forms.ModelForm):
    ALLOWED_CREATE_STATUSES = (Project.Status.PLANNED, Project.Status.ACTIVE)

    class Meta:
        model = Project
        fields = ["name", "description", "status", "start_date", "due_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (value, label)
            for value, label in Project.Status.choices
            if value in self.ALLOWED_CREATE_STATUSES
        ]
        self.fields["status"].initial = Project.Status.PLANNED

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        due_date = cleaned_data.get("due_date")

        if start_date and due_date and due_date < start_date:
            self.add_error(
                "due_date",
                "Due date cannot be earlier than the start date.",
            )

        return cleaned_data


class ProjectUpdateForm(ProjectForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = Project.Status.choices


class ProjectMemberForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Team member",
        empty_label="Select a user",
    )
    project_role = forms.ChoiceField(
        choices=ProjectMembership.Role.choices,
        label="Project role",
    )

    def __init__(self, *args, project, actor, **kwargs):
        super().__init__(*args, **kwargs)
        existing_member_ids = ProjectMembership.objects.filter(
            project=project
        ).values_list("user_id", flat=True)
        self.fields["user"].queryset = (
            User.objects.filter(
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            .exclude(pk__in=existing_member_ids)
            .exclude(pk=project.owner_id)
            .order_by("full_name", "email")
        )

        if not actor.is_admin:
            self.fields["project_role"].choices = [
                (ProjectMembership.Role.TEAM_MEMBER, "Team Member")
            ]
            self.fields["project_role"].initial = ProjectMembership.Role.TEAM_MEMBER
