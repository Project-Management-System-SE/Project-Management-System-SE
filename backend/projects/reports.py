import csv
import io
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from tasks.models import Task
from .models import Sprint, Milestone


def get_project_progress_metrics(project, start_date=None, end_date=None, sprint=None):
    """Calculates progress metrics including task counts, completion rate, and effort variance."""
    tasks_qs = project.tasks.all()
    if sprint:
        tasks_qs = tasks_qs.filter(sprint=sprint)
    if start_date:
        tasks_qs = tasks_qs.filter(created_at__date__gte=start_date)
    if end_date:
        tasks_qs = tasks_qs.filter(created_at__date__lte=end_date)

    total_tasks = tasks_qs.count()
    completed_tasks = tasks_qs.filter(status=Task.Status.DONE).count()
    in_progress_tasks = tasks_qs.filter(status=Task.Status.IN_PROGRESS).count()
    in_review_tasks = tasks_qs.filter(status=Task.Status.IN_REVIEW).count()
    todo_tasks = tasks_qs.filter(status=Task.Status.TODO).count()

    completion_rate = (
        round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0.0
    )

    total_estimated = tasks_qs.aggregate(s=Sum("estimated_effort"))["s"] or Decimal("0.00")
    total_actual = tasks_qs.aggregate(s=Sum("actual_effort"))["s"] or Decimal("0.00")
    effort_variance = total_actual - total_estimated

    today = timezone.localdate() if timezone.is_aware(timezone.now()) else timezone.now().date()
    overdue_tasks = (
        tasks_qs.filter(due_date__lt=today)
        .exclude(status=Task.Status.DONE)
        .count()
    )

    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "in_progress_tasks": in_progress_tasks,
        "in_review_tasks": in_review_tasks,
        "todo_tasks": todo_tasks,
        "completion_rate": completion_rate,
        "total_estimated": total_estimated,
        "total_actual": total_actual,
        "effort_variance": effort_variance,
        "overdue_tasks": overdue_tasks,
    }


def get_sprint_velocity_metrics(project):
    """Calculates sprint velocity trends and average delivery velocity across closed sprints."""
    sprints = project.sprints.all().order_by("start_date", "pk")
    sprint_data = []
    total_completed_effort = Decimal("0.00")
    closed_sprint_count = 0

    for s in sprints:
        completed_tasks = s.tasks.filter(status=Task.Status.DONE)
        completed_count = completed_tasks.count()
        completed_effort = completed_tasks.aggregate(s=Sum("actual_effort"))["s"] or Decimal("0.00")
        estimated_effort = s.tasks.aggregate(s=Sum("estimated_effort"))["s"] or Decimal("0.00")

        is_closed = (s.status == Sprint.Status.COMPLETED)
        if is_closed:
            closed_sprint_count += 1
            total_completed_effort += completed_effort

        sprint_data.append({
            "sprint": s,
            "name": s.name,
            "status": s.status,
            "total_tasks": s.tasks.count(),
            "completed_tasks": completed_count,
            "estimated_effort": estimated_effort,
            "completed_effort": completed_effort,
            "is_closed": is_closed,
        })

    avg_velocity = (
        round(total_completed_effort / closed_sprint_count, 2)
        if closed_sprint_count > 0
        else Decimal("0.00")
    )

    return {
        "sprints": sprint_data,
        "closed_sprint_count": closed_sprint_count,
        "total_completed_effort": total_completed_effort,
        "average_velocity": avg_velocity,
    }


def get_team_workload_metrics(project):
    """Calculates per-member workload distribution and effort allocation."""
    members = list(project.memberships.select_related("user").all())
    all_users = {m.user for m in members}
    all_users.add(project.owner)

    workload = []
    for u in sorted(all_users, key=lambda x: (x.full_name or x.username)):
        user_tasks = project.tasks.filter(assignee=u)
        total = user_tasks.count()
        completed = user_tasks.filter(status=Task.Status.DONE).count()
        active = user_tasks.filter(
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS, Task.Status.IN_REVIEW]
        ).count()
        est = user_tasks.aggregate(s=Sum("estimated_effort"))["s"] or Decimal("0.00")
        act = user_tasks.aggregate(s=Sum("actual_effort"))["s"] or Decimal("0.00")

        workload.append({
            "user": u,
            "name": u.full_name or u.username,
            "email": u.email,
            "total_tasks": total,
            "active_tasks": active,
            "completed_tasks": completed,
            "estimated_effort": est,
            "actual_effort": act,
        })

    unassigned_tasks = project.tasks.filter(assignee__isnull=True)
    if unassigned_tasks.exists():
        workload.append({
            "user": None,
            "name": "Unassigned",
            "email": "-",
            "total_tasks": unassigned_tasks.count(),
            "active_tasks": unassigned_tasks.exclude(status=Task.Status.DONE).count(),
            "completed_tasks": unassigned_tasks.filter(status=Task.Status.DONE).count(),
            "estimated_effort": unassigned_tasks.aggregate(s=Sum("estimated_effort"))["s"] or Decimal("0.00"),
            "actual_effort": unassigned_tasks.aggregate(s=Sum("actual_effort"))["s"] or Decimal("0.00"),
        })

    return workload
