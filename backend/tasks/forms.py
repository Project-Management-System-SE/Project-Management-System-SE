from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q

from projects.models import Milestone, Sprint

from .models import (
    Task,
    TaskAttachment,
    TaskComment,
    TaskLabel,
    task_attachment_max_size_label,
)
from .workflow import (
    allowed_status_transitions,
    initial_workflow_status,
    set_task_workflow_status,
    workflow_choices_for,
    workflow_states_for,
    validate_workflow_transition,
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
    sprint = forms.ModelChoiceField(
        queryset=Sprint.objects.none(),
        required=False,
        empty_label="All sprints",
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
        self.fields["sprint"].queryset = project.sprints.order_by(
            "-start_date", "-pk"
        )


class TaskForm(forms.ModelForm):
    status = forms.ChoiceField(choices=Task.Status.choices)
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
            current_status = (
                self.instance.workflow_state.key
                if self.instance.workflow_state_id
                else self.instance.status
            )
            if not self.is_bound:
                self.fields["labels"].initial = self.instance.get_labels_as_string()
        elif project:
            self.project = project
            current_status = None
        else:
            self.project = getattr(self.instance, "project", None)
            current_status = None

        workflow_states = workflow_states_for(self.project)
        choices = workflow_choices_for(self.project)
        if workflow_states and current_status is None:
            initial_status = initial_workflow_status(self.project)
            allowed_statuses = {initial_status}
            invalid_status_message = "New tasks must start in the workflow's initial state."
        elif current_status is None:
            allowed_statuses = {Task.Status.BACKLOG, Task.Status.TODO}
            invalid_status_message = "New tasks must start in Backlog or To Do."
        else:
            allowed_statuses = allowed_status_transitions(
                current_status,
                self.project,
            ) | {current_status}
            invalid_status_message = (
                "This status change is not allowed by the project workflow."
                if workflow_states
                or (
                    self.project
                    and self.project.workflow_transitions.exists()
                )
                else (
                    "This status change is not allowed by the default workflow. "
                    "Tasks must pass through Review before they can be marked Done."
                )
            )
        self.fields["status"].choices = [
            (value, label)
            for value, label in choices
            if value in allowed_statuses
        ]
        self.fields["status"].error_messages["invalid_choice"] = (
            invalid_status_message
        )
        if not self.is_bound:
            self.fields["status"].initial = (
                current_status
                if current_status is not None
                else (
                    initial_workflow_status(self.project)
                    if workflow_states
                    else Task.Status.TODO
                )
            )

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

    def clean_assignee(self):
        assignee = self.cleaned_data.get("assignee")
        if assignee and self.project:
            is_valid_assignee = (
                self.project.owner_id == assignee.pk
                or self.project.memberships.filter(user=assignee).exists()
            )
            if not is_valid_assignee:
                raise forms.ValidationError("Selected assignee must be an active member or owner of this project.")
        return assignee

    def clean_title(self):
        title = self.cleaned_data.get("title", "")
        if title:
            stripped = title.strip()
            if len(stripped) < 3:
                raise forms.ValidationError("Task title must be at least 3 characters long.")
            if "<script" in stripped.lower() or "javascript:" in stripped.lower():
                raise forms.ValidationError("Task title contains prohibited script elements.")
            return stripped
        return title

    def clean_due_date(self):
        due_date = self.cleaned_data.get("due_date")
        if due_date and self.project and self.project.start_date:
            if due_date < self.project.start_date:
                raise forms.ValidationError("Due date cannot precede the project start date.")
        return due_date

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
        status = cleaned_data.get("status")
        if status and self.instance and self.instance.pk:
            from .workflow import (
                validate_workflow_transition,
                workflow_status_key,
            )
            try:
                validate_workflow_transition(
                    workflow_status_key(self.instance),
                    status,
                    self.project,
                )
            except ValidationError as error:
                self.add_error("status", str(error))
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

    def _post_clean(self):
        status = self.cleaned_data.get("status")
        if status is None or not workflow_states_for(self.project):
            super()._post_clean()
            return

        self.instance.project = self.project
        set_task_workflow_status(self.instance, status, self.project)
        self.cleaned_data["status"] = self.instance.status
        try:
            super()._post_clean()
        finally:
            self.cleaned_data["status"] = status

    def save(self, commit=True):
        task = super().save(commit=False)
        if self.project and not getattr(task, "project_id", None):
            task.project = self.project
        set_task_workflow_status(
            task,
            self.cleaned_data["status"],
            self.project,
        )

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

    def __init__(self, *args, current_status, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_status = current_status
        self._project = project
        allowed_statuses = allowed_status_transitions(
            current_status,
            project,
        ) | {current_status}
        choices = workflow_choices_for(project)
        self.fields["status"].choices = [
            (value, label)
            for value, label in choices
            if value in allowed_statuses
        ]
        self.fields["status"].error_messages["invalid_choice"] = (
            "This status change is not allowed by the project workflow."
            if workflow_states_for(project)
            or (project and project.workflow_transitions.exists())
            else (
                "This status change is not allowed by the default workflow. "
                "Tasks must pass through Review before they can be marked Done."
            )
        )

    def clean_status(self):
        status = self.cleaned_data["status"]
        try:
            validate_workflow_transition(
                getattr(self, "_current_status", None),
                status,
                getattr(self, "_project", None),
            )
        except ValidationError:
            raise forms.ValidationError(
                "Tasks must enter Review before they can be marked Done."
            )
        return status


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
