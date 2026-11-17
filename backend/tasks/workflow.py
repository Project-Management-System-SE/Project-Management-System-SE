from django.core.exceptions import ValidationError

from .models import Task, WorkflowState, WorkflowTransition

STATUS_TRANSITIONS = {
    Task.Status.BACKLOG: {Task.Status.TODO},
    Task.Status.TODO: {Task.Status.BACKLOG, Task.Status.IN_PROGRESS},
    Task.Status.IN_PROGRESS: {Task.Status.TODO, Task.Status.REVIEW},
    Task.Status.REVIEW: {Task.Status.IN_PROGRESS, Task.Status.DONE},
    Task.Status.DONE: {Task.Status.REVIEW},
}


def workflow_states_for(project):
    if project is None or not project.pk:
        return []
    return list(project.workflow_states.all())


def workflow_choices_for(project):
    states = workflow_states_for(project)
    if states:
        return [(state.key, state.name) for state in states]
    return list(Task.Status.choices)


def initial_workflow_status(project):
    states = workflow_states_for(project)
    if states:
        initial_state = next((state for state in states if state.is_initial), None)
        if initial_state is None:
            raise ValidationError("The project workflow has no initial state.")
        return initial_state.key
    return Task.Status.TODO


def workflow_status_key(task):
    if task.workflow_state_id:
        return task.workflow_state.key
    return task.status


def task_status_for_workflow_state(state):
    if state.is_final:
        return Task.Status.DONE
    if state.key == Task.Status.DONE:
        return Task.Status.IN_PROGRESS
    if state.key in Task.Status.values:
        return state.key
    return Task.Status.TODO if state.is_initial else Task.Status.IN_PROGRESS


def set_task_workflow_status(task, status_key, project):
    states = workflow_states_for(project)
    if states:
        state = next((state for state in states if state.key == status_key), None)
        if state is None:
            raise ValidationError("Select a state from this project's workflow.")
        task.workflow_state = state
        task.status = task_status_for_workflow_state(state)
    else:
        task.workflow_state = None
        task.status = status_key


def allowed_status_transitions(status, project=None):
    states = workflow_states_for(project)
    if states:
        return set(
            WorkflowTransition.objects.filter(
                from_state__project=project,
                from_state__key=status,
            ).values_list("to_state__key", flat=True)
        )
    if status == Task.Status.BACKLOG:
        return STATUS_TRANSITIONS.get(status, set())
    if project and project.workflow_transitions.exists():
        from projects.workflow import get_allowed_transitions

        return set(get_allowed_transitions(project, status))
    return STATUS_TRANSITIONS.get(status, set())


def is_valid_workflow_transition(current_status, new_status, project, user=None):
    if current_status == new_status:
        return True
    if workflow_states_for(project):
        return new_status in allowed_status_transitions(current_status, project)
    if project and project.workflow_transitions.exists():
        from projects.workflow import is_valid_transition

        return is_valid_transition(
            project,
            current_status,
            new_status,
            user=user,
        )
    return new_status in allowed_status_transitions(current_status, project)
