from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q

from projects.models import Milestone, Sprint

from .models import (
    Task,
    TaskAttachment,
    TaskComment,
    TaskLabel,
    task_attachment_max_size_label,
)

User = get_user_model()


class TaskFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        max_length=100,
        label="Keyword",
        widget=forms.TextInput(attrs={"placeholder": "Task title or description"}),
    )
    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="All assignees",
    )
    priority = forms.ChoiceField(
        choices=(("", "All priorities"), *Task.Priority.choices),
        required=False,
    )
    status = forms.ChoiceField(
        choices=(("", "All statuses"), *Task.Status.choices),
        required=False,
    )
    label = forms.ModelChoiceField(
        queryset=TaskLabel.objects.none(),
        required=False,
        empty_label="All labels",
    )

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = (
            User.objects.filter(
                Q(project_memberships__project=project) | Q(owned_projects=project)
            )
            .distinct()
            .order_by("full_name", "email")
        )
        self.fields["label"].queryset = project.labels.order_by("name")


class TaskForm(forms.ModelForm):
    estimated_effort = forms.DecimalField(
        required=False,
        max_digits=7,
        decimal_places=2,
        min_value=0,
        label="Estimated effort (hours)",
        help_text="Optional decimal hours, such as 2.50 for two and a half hours.",
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    actual_effort = forms.DecimalField(
        required=False,
        max_digits=7,
        decimal_places=2,
        min_value=0,
        label="Actual effort (hours)",
        help_text="Optional decimal hours recorded for work completed.",
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
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
            "estimated_effort",
            "actual_effort",
            "sprint",
            "milestone",
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
            self.fields["sprint"].queryset = self.project.sprints.exclude(
                status=Sprint.Status.COMPLETED
            )
            self.fields["sprint"].empty_label = "Project backlog"
            self.fields["milestone"].queryset = self.project.milestones.all()
        else:
            self.fields["assignee"].queryset = User.objects.none()
            self.fields["assignee"].empty_label = "Unassigned"
            self.fields["sprint"].queryset = Sprint.objects.none()
            self.fields["milestone"].queryset = Milestone.objects.none()

    def clean_labels(self):
        raw_labels = self.cleaned_data.get("labels", "")
        if not raw_labels:
            return []

        tokens = [token.strip().lower() for token in raw_labels.split(",")]
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
            raise forms.ValidationError("A task cannot have more than 10 labels.")

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

        if commit:
            task.save()
            self._save_labels(task)
        else:
            self.save_m2m = lambda: self._save_labels(task)
        return task

    def _save_labels(self, task):
        cleaned_labels = self.cleaned_data.get("labels", [])
        label_objects = [
            TaskLabel.objects.get_or_create(project=task.project, name=name)[0]
            for name in cleaned_labels
        ]
        task.labels.set(label_objects)


class TaskStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Task.Status.choices)


class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Write a comment"}
            ),
        }


class TaskAttachmentForm(forms.ModelForm):
    file = forms.FileField(
        error_messages={"empty": "The uploaded file is empty."}
    )

    class Meta:
        model = TaskAttachment
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={
                    "accept": ",".join(
                        f".{extension}"
                        for extension in settings.TASK_ATTACHMENT_ALLOWED_EXTENSIONS
                    )
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_types = ", ".join(
            f".{extension}" for extension in settings.TASK_ATTACHMENT_ALLOWED_EXTENSIONS
        )
        self.fields["file"].help_text = (
            f"Allowed file types: {allowed_types}. "
            f"Maximum size: {task_attachment_max_size_label()}."
        )
