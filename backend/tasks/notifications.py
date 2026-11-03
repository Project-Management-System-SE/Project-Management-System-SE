from config.notifications import create_notifications


def notify_task_assignment(task):
    if not task.assignee:
        return

    create_notifications(
        title=f"Task assigned to you: {task.title}",
        message=(
            f"You have been assigned to '{task.title}' in project "
            f"'{task.project.name}'.\n"
            f"Due date: {task.due_date or 'Not set'}.\n"
        ),
        recipients=[task.assignee],
    )


def notify_task_status_change(task, actor):
    recipients = {
        user.pk: user
        for user in (task.assignee, task.created_by)
        if user and user.pk != actor.pk
    }
    if not recipients:
        return

    create_notifications(
        title=f"Task status changed: {task.title}",
        message=(
            f"The status of '{task.title}' in project '{task.project.name}' "
            f"was changed to {task.get_status_display()} by {actor.full_name}."
        ),
        recipients=recipients.values(),
    )


def notify_task_comment(task, comment):
    recipients = {
        user.pk: user
        for user in (task.assignee, task.created_by)
        if user and user.pk != comment.author_id
    }
    if not recipients:
        return

    create_notifications(
        title=f"New comment on task: {task.title}",
        message=(
            f"{comment.author.full_name} commented on '{task.title}' "
            f"in project '{task.project.name}':\n\n{comment.body}"
        ),
        recipients=recipients.values(),
    )
