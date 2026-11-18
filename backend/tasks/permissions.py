from projects.permissions import visible_projects_for


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
