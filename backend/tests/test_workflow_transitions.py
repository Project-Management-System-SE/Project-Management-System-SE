from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from projects.models import Project, ProjectMembership, ProjectWorkflowTransition
from projects.workflow import (
    get_allowed_transitions,
    is_valid_transition,
    validate_status_transition,
)
from tasks.models import Task

User = get_user_model()


class WorkflowTransitionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="wf_owner",
            email="wf_owner@example.com",
            full_name="Workflow Owner",
            password="password123",
        )
        self.project = Project.objects.create(
            name="Workflow Test Project",
            owner=self.owner,
            status=Project.Status.ACTIVE,
        )
        self.task = Task.objects.create(
            title="Workflow Task",
            project=self.project,
            created_by=self.owner,
            status=Task.Status.TODO,
        )

    def test_default_valid_transitions(self):
        self.assertTrue(is_valid_transition(self.project, "TODO", "IN_PROGRESS"))
        self.assertTrue(is_valid_transition(self.project, "IN_PROGRESS", "DONE"))
        self.assertTrue(is_valid_transition(self.project, "IN_PROGRESS", "TODO"))
        self.assertTrue(is_valid_transition(self.project, "DONE", "IN_PROGRESS"))

    def test_default_invalid_transitions(self):
        self.assertFalse(is_valid_transition(self.project, "TODO", "DONE"))
        self.assertFalse(is_valid_transition(self.project, "DONE", "TODO"))

    def test_same_status_is_always_valid(self):
        self.assertTrue(is_valid_transition(self.project, "TODO", "TODO"))
        self.assertTrue(is_valid_transition(self.project, "DONE", "DONE"))

    def test_validate_status_transition_raises_error(self):
        with self.assertRaises(ValidationError):
            validate_status_transition(self.task, "DONE")

    def test_custom_project_workflow_override(self):
        ProjectWorkflowTransition.objects.create(
            project=self.project,
            from_status="TODO",
            to_status="DONE",
            is_allowed=True,
            description="Fast track allowed",
        )
        self.assertTrue(is_valid_transition(self.project, "TODO", "DONE"))
