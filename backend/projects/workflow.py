from django.core.exceptions import ValidationError

DEFAULT_WORKFLOW_TRANSITIONS = {
    "TODO": ["IN_PROGRESS"],
    "IN_PROGRESS": ["IN_REVIEW", "TODO"],
    "IN_REVIEW": ["DONE", "IN_PROGRESS"],
    "DONE": ["IN_PROGRESS"],
}

STATUS_CHOICES = ["TODO", "IN_PROGRESS", "IN_REVIEW", "DONE"]


def get_default_transitions_map():
    return {k: list(v) for k, v in DEFAULT_WORKFLOW_TRANSITIONS.items()}


def get_allowed_transitions(project, current_status):
    """Returns the list of valid next statuses for a given task status in the project."""
    if not project:
        return DEFAULT_WORKFLOW_TRANSITIONS.get(current_status, [])

    transitions = project.workflow_transitions.filter(from_status=current_status)
    if transitions.exists():
        allowed = list(
            transitions.filter(is_allowed=True).values_list("to_status", flat=True)
        )
        return allowed

    return DEFAULT_WORKFLOW_TRANSITIONS.get(current_status, [])


def is_valid_transition(project, from_status, to_status):
    """Validates whether transitioning from from_status to to_status is allowed."""
    if from_status == to_status:
        return True

    allowed_targets = get_allowed_transitions(project, from_status)
    return to_status in allowed_targets


def validate_status_transition(task, new_status):
    """Raises ValidationError if the attempted status transition is disallowed."""
    if task.status == new_status:
        return

    if not is_valid_transition(task.project, task.status, new_status):
        raise ValidationError(
            f"Transition from {task.get_status_display()} to {new_status} is not allowed by project workflow rules."
        )
