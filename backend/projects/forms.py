from django import forms

from .models import Project


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
