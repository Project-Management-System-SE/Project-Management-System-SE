from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from .models import Task, TaskLabel

User = get_user_model()


class TaskForm(forms.ModelForm):
    labels = forms.CharField(
        required=False,
        help_text="Comma-separated labels (e.g. bug, frontend, urgent).",
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. bug, frontend, urgent"}
        ),
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "priority",
            "due_date",
            "assignee",
            "status",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.project = self.instance.project
            if not self.is_bound:
                self.fields["labels"].initial = self.instance.get_labels_as_string()
        elif project:
            self.project = project
        else:
            self.project = getattr(self.instance, "project", None)

        if self.project:
            eligible_users = User.objects.filter(
                Q(project_memberships__project=self.project)
                | Q(owned_projects=self.project)
            ).distinct().order_by("full_name", "email")
            self.fields["assignee"].queryset = eligible_users
            self.fields["assignee"].empty_label = "Unassigned"
        else:
            self.fields["assignee"].queryset = User.objects.none()
            self.fields["assignee"].empty_label = "Unassigned"

    def clean_labels(self):
        raw_labels = self.cleaned_data.get("labels", "")
        if not raw_labels:
            return []

        tokens = [t.strip().lower() for t in raw_labels.split(",")]
        cleaned_tokens = []
        seen = set()

        for token in tokens:
            if not token:
                continue
            if len(token) > 50:
                raise forms.ValidationError(
                    f"Label '{token}' exceeds the maximum length of 50 characters."
                )
            if token not in seen:
                seen.add(token)
                cleaned_tokens.append(token)

        if len(cleaned_tokens) > 10:
            raise forms.ValidationError(
                "A task cannot have more than 10 labels."
            )

        return cleaned_tokens

    def clean(self):
        cleaned_data = super().clean()
        assignee = cleaned_data.get("assignee")
        if assignee and self.project:
            is_member = (
                self.project.memberships.filter(user=assignee).exists()
                or self.project.owner_id == assignee.pk
            )
            if not is_member:
                self.add_error(
                    "assignee",
                    "Selected assignee is not an authorized member of this project.",
                )
        return cleaned_data

    def save(self, commit=True):
        task = super().save(commit=False)
        if self.project and not getattr(task, "project_id", None):
            task.project = self.project

        def save_m2m():
            self._save_labels(task)

        if commit:
            task.save()
            save_m2m()
        else:
            self.save_m2m = save_m2m

        return task

    def _save_labels(self, task):
        cleaned_labels = self.cleaned_data.get("labels", [])
        label_objs = []
        for name in cleaned_labels:
            label_obj, _ = TaskLabel.objects.get_or_create(
                project=task.project,
                name=name,
            )
            label_objs.append(label_obj)
        task.labels.set(label_objs)
