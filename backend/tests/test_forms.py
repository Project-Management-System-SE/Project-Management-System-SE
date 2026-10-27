from datetime import date

from django.test import TestCase

from projects.forms import ProjectForm
from projects.models import Project


class ProjectFormTests(TestCase):
    def test_valid_project_data_is_accepted(self):
        form = ProjectForm(
            data={
                "name": "PMS",
                "description": "Project management system",
                "status": Project.Status.ACTIVE,
                "start_date": "2026-10-01",
                "due_date": "2026-10-31",
            }
        )

        self.assertTrue(form.is_valid())

    def test_name_is_required(self):
        form = ProjectForm(
            data={
                "name": "",
                "description": "",
                "status": Project.Status.PLANNED,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_name_length_boundary_is_enforced(self):
        valid_form = ProjectForm(
            data={
                "name": "P" * 200,
                "description": "",
                "status": Project.Status.PLANNED,
            }
        )
        invalid_form = ProjectForm(
            data={
                "name": "P" * 201,
                "description": "",
                "status": Project.Status.PLANNED,
            }
        )

        self.assertTrue(valid_form.is_valid())
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("name", invalid_form.errors)

    def test_description_may_be_blank(self):
        form = ProjectForm(
            data={
                "name": "PMS",
                "description": "",
                "status": Project.Status.PLANNED,
            }
        )

        self.assertTrue(form.is_valid())

    def test_only_planned_and_active_statuses_are_offered(self):
        form = ProjectForm()

        self.assertEqual(
            [value for value, _ in form.fields["status"].choices],
            [Project.Status.PLANNED, Project.Status.ACTIVE],
        )

    def test_archived_status_cannot_be_selected_at_creation(self):
        form = ProjectForm(
            data={
                "name": "PMS",
                "description": "",
                "status": Project.Status.ARCHIVED,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_status_must_be_a_documented_choice(self):
        form = ProjectForm(
            data={
                "name": "PMS",
                "description": "",
                "status": "UNKNOWN",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_due_date_cannot_precede_start_date(self):
        form = ProjectForm(
            data={
                "name": "PMS",
                "description": "",
                "status": Project.Status.PLANNED,
                "start_date": "2026-10-10",
                "due_date": "2026-10-01",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("due_date", form.errors)
        self.assertIn(
            "Due date cannot be earlier than the start date.",
            form.errors["due_date"],
        )

    def test_dates_are_optional(self):
        form = ProjectForm(
            data={
                "name": "PMS",
                "description": "",
                "status": Project.Status.PLANNED,
                "start_date": "",
                "due_date": "",
            }
        )

        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["start_date"])
        self.assertIsNone(form.cleaned_data["due_date"])

    def test_equal_start_and_due_dates_are_allowed(self):
        form = ProjectForm(
            data={
                "name": "PMS",
                "description": "",
                "status": Project.Status.PLANNED,
                "start_date": date(2026, 10, 1).isoformat(),
                "due_date": date(2026, 10, 1).isoformat(),
            }
        )

        self.assertTrue(form.is_valid())
