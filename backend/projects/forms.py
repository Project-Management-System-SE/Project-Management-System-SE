from django import forms

from accounts.models import User

from .models import Milestone, Project, ProjectMembership, Sprint


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


class SprintForm(forms.ModelForm):
    class Meta:
        model = Sprint
        fields = ["name", "goal", "start_date", "end_date", "status"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        status = cleaned_data.get("status")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date cannot be earlier than the start date.")
        if self.instance.pk:
            current_status = self.instance.status
            allowed = {
                Sprint.Status.PLANNED: {
                    Sprint.Status.PLANNED,
                    Sprint.Status.ACTIVE,
                },
                Sprint.Status.ACTIVE: {Sprint.Status.ACTIVE},
                Sprint.Status.COMPLETED: {Sprint.Status.COMPLETED},
            }
            if status not in allowed.get(current_status, {current_status}):
                self.add_error("status", "Use the sprint lifecycle actions to change this status.")
        elif status != Sprint.Status.PLANNED:
            self.add_error("status", "New sprints must start in Planned status.")
        return cleaned_data

    def save(self, commit=True):
        sprint = super().save(commit=False)
        sprint.project = self.project
        if commit:
            sprint.save()
        return sprint


class MilestoneForm(forms.ModelForm):
    class Meta:
        model = Milestone
        fields = ["name", "description", "target_date", "status"]
        widgets = {"target_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def save(self, commit=True):
        milestone = super().save(commit=False)
        milestone.project = self.project
        if commit:
            milestone.save()
        return milestone
