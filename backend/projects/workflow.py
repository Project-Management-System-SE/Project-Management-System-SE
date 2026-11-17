from django.core.exceptions import ValidationError
from projects.permissions import can_manage_project

DEFAULT_WORKFLOW_TRANSITIONS = {
    "TODO": ["IN_PROGRESS"],
    "IN_PROGRESS": ["DONE", "TODO"],
    "DONE": ["IN_PROGRESS"],
}

STATUS_CHOICES = ["TODO", "IN_PROGRESS", "DONE"]


def _legacy_status(status):
    return "IN_REVIEW" if status == "REVIEW" else status


def _task_status(status):
    return "REVIEW" if status == "IN_REVIEW" else status


def get_default_transitions_map():
    return {k: list(v) for k, v in DEFAULT_WORKFLOW_TRANSITIONS.items()}


def get_allowed_transitions(project, current_status):
    """Returns the list of valid next statuses for a given task status in the project."""
    current_status = _legacy_status(current_status)
    if not project:
        return [
            _task_status(status)
            for status in DEFAULT_WORKFLOW_TRANSITIONS.get(current_status, [])
        ]

    if project.workflow_transitions.exists():
        allowed_statuses = project.workflow_transitions.filter(
            from_status=current_status,
            is_allowed=True,
        ).values_list("to_status", flat=True)
        return [_task_status(status) for status in allowed_statuses]

    return [
        _task_status(status)
        for status in DEFAULT_WORKFLOW_TRANSITIONS.get(current_status, [])
    ]


def is_valid_transition(project, from_status, to_status, user=None):
    """Validates whether transitioning from from_status to to_status is allowed."""
    from_status = _legacy_status(from_status)
    to_status = _legacy_status(to_status)
    if from_status == to_status:
        return True
    if from_status == "BACKLOG" and to_status == "TODO":
        return True

    # If project has custom workflow transitions configured, enforce them strictly
    if project and project.workflow_transitions.exists():
        allowed_targets = list(
            project.workflow_transitions.filter(
                from_status=from_status, is_allowed=True
            ).values_list("to_status", flat=True)
        )
        return to_status in allowed_targets

    # By default, project managers / owners can manage task workflow freely
    if user and can_manage_project(user, project):
        return True

    # Standard team members follow default lifecycle transitions
    allowed_targets = DEFAULT_WORKFLOW_TRANSITIONS.get(from_status, [])
    return to_status in allowed_targets


def validate_status_transition(task, new_status, user=None):
    """Raises ValidationError if the attempted status transition is disallowed."""
    if task.status == new_status:
        return

    if not is_valid_transition(task.project, task.status, new_status, user=user):
        raise ValidationError(
            f"Transition from {task.get_status_display()} to {new_status} is not allowed by project workflow rules."
        )
