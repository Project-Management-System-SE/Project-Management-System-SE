from projects.permissions import can_manage_project, visible_projects_for


def can_view_tasks_for(user, project):
    if not user.is_authenticated:
        return False
    return visible_projects_for(user).filter(pk=project.pk).exists()


def can_create_task_in(user, project):
    return can_view_tasks_for(user, project)


def can_edit_task(user, task):
    if not user.is_authenticated or not user.is_active:
        return False
    return can_view_tasks_for(user, task.project)


def can_reassign_task(user, task):
    """Only project managers, owners, and system admins can reassign tasks."""
    if not user.is_authenticated:
        return False
    return can_manage_project(user, task.project)


def can_delete_task(user, task):
    """Only project managers, owners, and system admins can delete tasks."""
    if not user.is_authenticated:
        return False
    return can_manage_project(user, task.project)
