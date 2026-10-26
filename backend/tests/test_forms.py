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
