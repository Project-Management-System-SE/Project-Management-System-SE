from projects.permissions import can_manage_project, visible_projects_for


def can_view_tasks_for(user, project):
    if not user.is_authenticated:
        return False
    return visible_projects_for(user).filter(pk=project.pk).exists()


def can_create_task_in(user, project):
    if not user.is_authenticated:
        return False
    return can_manage_project(user, project)


def can_edit_task(user, task):
    if not user.is_authenticated:
        return False
    if can_manage_project(user, task.project):
        return True
    is_active_member = task.project.memberships.filter(user=user).exists()
    if is_active_member and (task.assignee_id == user.pk or task.created_by_id == user.pk):
        return True
    return False
