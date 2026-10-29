from django import forms

from .models import Task


class TaskStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Task.Status.choices)
