from datetime import date

from django import forms
from django.template.loader import render_to_string
from django.test import SimpleTestCase


class TaskFormStub(forms.Form):
    title = forms.CharField(help_text="Short task title.")
    description = forms.CharField(required=False, widget=forms.Textarea)
    priority = forms.ChoiceField(
        choices=[("LOW", "Low"), ("HIGH", "High")],
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    assignee = forms.ChoiceField(
        choices=[("1", "Alice")],
        required=False,
    )
    status = forms.ChoiceField(choices=[("TODO", "To do")])
    labels = forms.CharField(
        required=False,
        help_text="Labels are supplied by the backend.",
    )


class TaskFormTemplateTests(SimpleTestCase):
    def render_form(self, form, **context):
        return render_to_string(
            "task_form.html",
            {
                "form": form,
                "csrf_token": "test-csrf-token",
                **context,
            },
        )

    def test_renders_supplied_fields_help_text_errors_and_csrf(self):
        form = TaskFormStub(
            data={
                "title": "",
                "description": "",
                "priority": "HIGH",
                "due_date": "",
                "assignee": "",
                "status": "TODO",
                "labels": "",
            }
        )

        html = self.render_form(
            form,
            form_heading="Create task",
            submit_label="Create task",
        )

        for field_name in (
            "title",
            "description",
            "priority",
            "due_date",
            "assignee",
            "status",
            "labels",
        ):
            self.assertIn(f'name="{field_name}"', html)

        self.assertIn('name="csrfmiddlewaretoken"', html)
        self.assertIn('value="test-csrf-token"', html)
        self.assertIn("Short task title.", html)
        self.assertIn('id="id_title_help"', html)
        self.assertIn('id="id_title_errors"', html)
        self.assertIn('aria-invalid="true"', html)
        self.assertIn(
            'aria-describedby="id_title_help id_title_errors"',
            html,
        )
        self.assertIn("This field is required.", html)
        self.assertIn("Create task", html)

    def test_edit_mode_uses_bound_initial_values(self):
        form = TaskFormStub(
            initial={
                "title": "Existing task",
                "description": "Existing description",
                "priority": "HIGH",
                "due_date": date(2026, 11, 1),
                "assignee": "1",
                "status": "TODO",
                "labels": "frontend, urgent",
            }
        )

        html = self.render_form(
            form,
            form_heading="Edit task",
            submit_label="Save changes",
        )

        self.assertIn('value="Existing task"', html)
        self.assertIn("Existing description", html)
        self.assertIn('value="frontend, urgent"', html)
        self.assertIn('value="HIGH" selected', html)
        self.assertIn('aria-describedby="id_labels_help"', html)
        self.assertIn("Edit task", html)
        self.assertIn("Save changes", html)

    def test_renders_non_field_and_general_save_errors(self):
        form = TaskFormStub(
            data={
                "title": "Existing task",
                "description": "",
                "priority": "LOW",
                "due_date": "",
                "assignee": "",
                "status": "TODO",
                "labels": "",
            }
        )
        form.add_error(None, "Task could not be saved.")

        html = self.render_form(
            form,
            form_heading="Edit task",
            submit_label="Save changes",
            save_error="Could not save the task. Please try again.",
        )

        self.assertIn("Task could not be saved.", html)
        self.assertIn("Could not save the task. Please try again.", html)
        self.assertIn('role="alert"', html)

    def test_cancel_link_is_rendered_when_cancel_url_is_provided(self):
        form = TaskFormStub()

        html = self.render_form(
            form,
            cancel_url="/projects/",
            cancel_label="Back to projects",
        )

        self.assertIn('href="/projects/"', html)
        self.assertIn("Back to projects", html)

    def test_empty_fallback_message_when_form_has_no_visible_fields(self):
        # A form with no visible fields should display the empty-state message
        # rather than crashing or rendering nothing.
        empty_form = forms.Form()  # no fields at all

        html = self.render_form(empty_form)

        self.assertIn("No task fields are available yet.", html)
