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

    def test_invalid_priority_status_and_assignee_display_field_errors(self):
        form = TaskFormStub(
            data={
                "title": "A valid title",
                "description": "Some description",
                "priority": "NONEXISTENT_PRIORITY",
                "due_date": "2026-11-01",
                "assignee": "999",
                "status": "NONEXISTENT_STATUS",
                "labels": "backend",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("priority", form.errors)
        self.assertIn("assignee", form.errors)
        self.assertIn("status", form.errors)

        html = self.render_form(
            form,
            form_heading="Create task",
            submit_label="Create task",
        )

        # Field error elements must exist beside their fields
        self.assertIn('id="id_priority_errors"', html)
        self.assertIn('id="id_assignee_errors"', html)
        self.assertIn('id="id_status_errors"', html)

        # Elements should be marked with role="alert"
        self.assertIn('class="field-errors"', html)

        # Select inputs should have aria-invalid and aria-describedby referencing their error IDs
        self.assertIn('name="priority"', html)
        self.assertIn('aria-invalid="true"', html)
        self.assertIn('aria-describedby="id_priority_errors"', html)
        self.assertIn('aria-describedby="id_assignee_errors"', html)
        self.assertIn('aria-describedby="id_status_errors"', html)

    def test_preserves_entered_values_on_validation_failure(self):
        # When validation fails (e.g., missing required title), valid fields that
        # the user entered must retain their entered values.
        form = TaskFormStub(
            data={
                "title": "",  # missing required title
                "description": "Retained description text",
                "priority": "HIGH",
                "due_date": "2026-12-25",
                "assignee": "1",
                "status": "TODO",
                "labels": "retained-tag, high-priority",
            }
        )
        self.assertFalse(form.is_valid())

        html = self.render_form(form)

        # Field errors appear for title
        self.assertIn('id="id_title_errors"', html)
        self.assertIn("This field is required.", html)

        # Previously entered values are preserved in form fields
        self.assertIn("Retained description text", html)
        self.assertIn('value="HIGH" selected', html)
        self.assertIn('value="2026-12-25"', html)
        self.assertIn('value="1" selected', html)
        self.assertIn('value="TODO" selected', html)
        self.assertIn('value="retained-tag, high-priority"', html)

    def test_hidden_fields_render_inside_form(self):
        class FormWithHiddenField(TaskFormStub):
            project_id = forms.CharField(
                widget=forms.HiddenInput,
                initial="42",
            )

        form = FormWithHiddenField()
        html = self.render_form(form)

        self.assertIn('type="hidden" name="project_id" value="42"', html)

    def test_custom_page_heading_form_intro_and_action(self):
        form = TaskFormStub()
        html = self.render_form(
            form,
            page_heading="Create Sprint Task",
            form_heading="Sprint Task Details",
            form_intro="Assign this task to a sprint teammate.",
            form_action="/projects/1/tasks/new/",
        )

        self.assertIn("<title>Create Sprint Task | PMS</title>", html)
        self.assertIn("<h1>Create Sprint Task</h1>", html)
        self.assertIn("Sprint Task Details", html)
        self.assertIn("Assign this task to a sprint teammate.", html)
        self.assertIn('action="/projects/1/tasks/new/"', html)

    def test_accessible_widget_preserves_existing_aria_describedby(self):
        class FormWithCustomDescribedBy(forms.Form):
            notes = forms.CharField(
                help_text="Some helpful text.",
                widget=forms.TextInput(
                    attrs={"aria-describedby": "external-guidelines"}
                ),
            )

        form = FormWithCustomDescribedBy(data={"notes": ""})
        self.assertFalse(form.is_valid())

        html = self.render_form(form)

        # Should combine existing describedby with the generated help and error IDs
        self.assertIn(
            'aria-describedby="external-guidelines id_notes_help id_notes_errors"',
            html,
        )

    def test_multipart_enctype_rendered_when_form_is_multipart(self):
        class MultipartTaskForm(TaskFormStub):
            attachment = forms.FileField(required=False)

        form = MultipartTaskForm()
        self.assertTrue(form.is_multipart())

        html = self.render_form(form)
        self.assertIn('enctype="multipart/form-data"', html)

    def test_required_field_indicator_includes_accessible_label(self):
        form = TaskFormStub()
        html = self.render_form(form)

        # Title is required, so it should render both visual asterisk and accessible text
        self.assertIn('<span aria-hidden="true">*</span>', html)
        self.assertIn('<span class="visually-hidden"> (required)</span>', html)
