import csv
import io
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET

from tasks.models import Task
from .models import Sprint
from .permissions import visible_projects_for

EFFORT_FIELD = DecimalField(max_digits=12, decimal_places=2)


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
        "todo_tasks": todo_tasks,
        "completion_rate": completion_rate,
        "total_estimated": total_estimated,
        "total_actual": total_actual,
        "effort_variance": effort_variance,
        "overdue_tasks": overdue_tasks,
    }


def build_sprint_burndown(sprint, as_of=None):
    """Build a limited burndown from current tasks' saved completion timestamps.

    The task model does not retain daily status/estimate snapshots. Reopened tasks
    and historical estimate or sprint-assignment changes therefore cannot be
    reconstructed reliably from this data.
    """
    as_of = as_of or timezone.localdate()
    tasks = list(
        sprint.tasks.filter(project_id=sprint.project_id).only(
            "status", "estimated_effort", "completed_at"
        )
    )
    estimated_tasks = [task for task in tasks if task.estimated_effort is not None]
    estimated_effort = sum(
        (task.estimated_effort for task in estimated_tasks), Decimal("0.00")
    )
    current_remaining_effort = sum(
        (
            task.estimated_effort
            for task in tasks
            if task.status != Task.Status.DONE and task.estimated_effort is not None
        ),
        Decimal("0.00"),
    )
    completion_dates = {
        task.pk: timezone.localtime(task.completed_at).date()
        for task in tasks
        if task.status == Task.Status.DONE and task.completed_at is not None
    }

    sprint_started = (
        sprint.status != Sprint.Status.PLANNED and sprint.start_date <= as_of
    )
    chart_end_date = (
        sprint.end_date
        if sprint.status == Sprint.Status.COMPLETED
        else min(sprint.end_date, as_of)
    )
    has_completion_data = any(
        task.estimated_effort is not None
        and completion_dates.get(task.pk) is not None
        and completion_dates[task.pk] <= chart_end_date
        for task in tasks
    )
    chart_available = bool(
        tasks
        and estimated_tasks
        and sprint_started
        and has_completion_data
    )
    points = []
    if chart_available:
        day_count = (chart_end_date - sprint.start_date).days
        dates = [
            sprint.start_date + timedelta(days=offset)
            for offset in range(day_count + 1)
        ]
        if estimated_effort:
            max_effort = estimated_effort
        else:
            max_effort = Decimal("1.00")

        for date_index, point_date in enumerate(dates):
            completed_effort = sum(
                (
                    task.estimated_effort
                    for task in estimated_tasks
                    if completion_dates.get(task.pk) is not None
                    and completion_dates[task.pk] <= point_date
                ),
                Decimal("0.00"),
            )
            actual_remaining = estimated_effort - completed_effort
            if day_count:
                ideal_remaining = (
                    estimated_effort
                    * Decimal(day_count - date_index)
                    / Decimal(day_count)
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                ideal_remaining = Decimal("0.00")

            points.append(
                {
                    "date": point_date,
                    "ideal_remaining": ideal_remaining,
                    "actual_remaining": actual_remaining,
                }
            )

        chart_width = Decimal("560")
        chart_height = Decimal("160")
        for point_index, point in enumerate(points):
            point["x"] = (
                Decimal("300")
                if len(points) == 1
                else Decimal("20")
                + chart_width * Decimal(point_index) / Decimal(len(points) - 1)
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            point["ideal_y"] = (
                Decimal("20")
                + chart_height
                * (Decimal("1") - point["ideal_remaining"] / max_effort)
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            point["actual_y"] = (
                Decimal("20")
                + chart_height
                * (Decimal("1") - point["actual_remaining"] / max_effort)
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    return {
        "task_count": len(tasks),
        "estimated_task_count": len(estimated_tasks),
        "missing_estimate_count": len(tasks) - len(estimated_tasks),
        "estimated_effort": estimated_effort,
        "current_remaining_effort": current_remaining_effort,
        "current_remaining_missing_estimate_count": sum(
            task.status != Task.Status.DONE and task.estimated_effort is None
            for task in tasks
        ),
        "chart_available": chart_available,
        "chart_points": points,
        "has_limited_history": True,
        "sprint_started": sprint_started,
        "has_completion_data": has_completion_data,
    }


def get_sprint_velocity_metrics(project):
    """Report completed-task estimated hours as sprint velocity.

    A sprint with unestimated completed tasks has a known partial estimate but no
    complete velocity value. Average velocity excludes those incomplete sprints.
    """
    completed_task_filter = Q(
        tasks__project_id=project.pk,
        tasks__status=Task.Status.DONE,
    )
    sprints = project.sprints.annotate(
        total_tasks=Count(
            "tasks",
            filter=Q(tasks__project_id=project.pk),
            distinct=True,
        ),
        completed_tasks=Count("tasks", filter=completed_task_filter, distinct=True),
        estimated_task_count=Count(
            "tasks",
            filter=completed_task_filter & Q(tasks__estimated_effort__isnull=False),
            distinct=True,
        ),
        known_estimated_effort=Sum(
            "tasks__estimated_effort",
            filter=completed_task_filter,
        ),
        total_estimated_effort=Sum(
            "tasks__estimated_effort",
            filter=Q(tasks__project_id=project.pk),
        ),
        completed_actual_effort=Sum(
            "tasks__actual_effort",
            filter=completed_task_filter,
        ),
    ).order_by("start_date", "pk")
    sprint_data = []
    completed_sprint_count = 0
    complete_velocity_sprint_count = 0
    incomplete_sprint_count = 0
    total_velocity = Decimal("0.00")
    total_completed_effort = Decimal("0.00")

    for s in sprints:
        is_closed = (s.status == Sprint.Status.COMPLETED)
        known_estimated_effort = s.known_estimated_effort or Decimal("0.00")
        missing_estimate_count = s.completed_tasks - s.estimated_task_count
        velocity = (
            known_estimated_effort if missing_estimate_count == 0 else None
        )
        if is_closed:
            completed_sprint_count += 1
            total_completed_effort += (
                s.completed_actual_effort or Decimal("0.00")
            )
            if velocity is None:
                incomplete_sprint_count += 1
            else:
                complete_velocity_sprint_count += 1
                total_velocity += velocity

        sprint_data.append({
            "sprint": s,
            "name": s.name,
            "status": s.status,
            "total_tasks": s.total_tasks,
            "completed_tasks": s.completed_tasks,
            "estimated_effort": s.total_estimated_effort or Decimal("0.00"),
            "estimated_task_count": s.estimated_task_count,
            "missing_estimate_count": missing_estimate_count,
            "velocity": velocity,
            "known_estimated_effort": known_estimated_effort,
            "completed_effort": s.completed_actual_effort or Decimal("0.00"),
            "is_closed": is_closed,
        })

    average_velocity = None
    if complete_velocity_sprint_count:
        average_velocity = (total_velocity / complete_velocity_sprint_count).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return {
        "sprints": sprint_data,
        "closed_sprint_count": completed_sprint_count,
        "completed_sprint_count": completed_sprint_count,
        "velocity_sprint_count": complete_velocity_sprint_count,
        "incomplete_sprint_count": incomplete_sprint_count,
        "total_completed_effort": total_completed_effort,
        "total_velocity": total_velocity,
        "average_velocity": average_velocity,
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
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]
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


def generate_tasks_report_csv(project, start_date=None, end_date=None, sprint=None):
    """Generates a comprehensive CSV export of task records for the selected filters."""
    tasks_qs = project.tasks.select_related("assignee", "sprint", "milestone").order_by("pk")
    if sprint:
        tasks_qs = tasks_qs.filter(sprint=sprint)
    if start_date:
        tasks_qs = tasks_qs.filter(created_at__date__gte=start_date)
    if end_date:
        tasks_qs = tasks_qs.filter(created_at__date__lte=end_date)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Task ID",
        "Project",
        "Title",
        "Status",
        "Priority",
        "Assignee",
        "Sprint",
        "Milestone",
        "Estimated Hours",
        "Actual Hours",
        "Due Date",
        "Created At",
        "Updated At",
    ])

    for t in tasks_qs:
        writer.writerow([
            t.pk,
            project.name,
            t.title,
            t.status,
            t.priority,
            t.assignee.full_name if t.assignee else "Unassigned",
            t.sprint.name if t.sprint else "Backlog",
            t.milestone.name if t.milestone else "None",
            str(t.estimated_effort or "0.00"),
            str(t.actual_effort or "0.00"),
            t.due_date.isoformat() if t.due_date else "",
            t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else "",
            t.updated_at.strftime("%Y-%m-%d %H:%M:%S") if t.updated_at else "",
        ])

    return output.getvalue()


def generate_summary_report_csv(project):
    """Generates an executive summary CSV containing progress KPIs, velocity, and workload."""
    progress = get_project_progress_metrics(project)
    velocity = get_sprint_velocity_metrics(project)
    workload = get_team_workload_metrics(project)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["PROJECT SUMMARY REPORT"])
    writer.writerow(["Project Name", project.name])
    writer.writerow(["Status", project.status])
    writer.writerow(["Owner", project.owner.full_name or project.owner.username])
    writer.writerow(["Generated At", timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")])
    writer.writerow([])

    writer.writerow(["PROGRESS METRICS"])
    writer.writerow(["Total Tasks", progress["total_tasks"]])
    writer.writerow(["Completed Tasks", progress["completed_tasks"]])
    writer.writerow(["In Progress Tasks", progress["in_progress_tasks"]])
    writer.writerow(["To Do Tasks", progress["todo_tasks"]])
    writer.writerow(["Completion Rate", f"{progress['completion_rate']}%"])
    writer.writerow(["Total Estimated Hours", progress["total_estimated"]])
    writer.writerow(["Total Actual Hours", progress["total_actual"]])
    writer.writerow(["Effort Variance (Hours)", progress["effort_variance"]])
    writer.writerow(["Overdue Tasks", progress["overdue_tasks"]])
    writer.writerow([])

    writer.writerow(["SPRINT VELOCITY METRICS"])
    writer.writerow(["Closed Sprints Count", velocity["closed_sprint_count"]])
    writer.writerow([
        "Average Velocity (Estimated Hours per Fully Estimated Completed Sprint)",
        velocity["average_velocity"] if velocity["average_velocity"] is not None else "Incomplete data",
    ])
    writer.writerow([
        "Sprint Name",
        "Status",
        "Total Tasks",
        "Completed Tasks",
        "Velocity (Estimated Hours)",
        "Completed Actual Effort (Hours)",
        "Completed Tasks Missing Estimate",
    ])
    for s in velocity["sprints"]:
        writer.writerow([
            s["name"],
            s["status"],
            s["total_tasks"],
            s["completed_tasks"],
            s["velocity"] if s["velocity"] is not None else "Incomplete data",
            s["completed_effort"],
            s["missing_estimate_count"],
        ])
    writer.writerow([])

    writer.writerow(["TEAM WORKLOAD DISTRIBUTION"])
    writer.writerow(["Member Name", "Email", "Total Tasks", "Active Tasks", "Completed Tasks", "Estimated Hours", "Actual Hours"])
    for m in workload:
        writer.writerow([m["name"], m["email"], m["total_tasks"], m["active_tasks"], m["completed_tasks"], m["estimated_effort"], m["actual_effort"]])

    return output.getvalue()
def _safe_csv_cell(value):
    if isinstance(value, str) and value.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@"):
        return f"'{value}"
    return value


def _csv_response(filename, headers, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(
        [_safe_csv_cell(value) for value in row]
        for row in rows
    )
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _visible_project_or_404(user, project_id):
    return get_object_or_404(visible_projects_for(user), pk=project_id)


@login_required
@require_GET
def project_progress_report(request, project_id):
    project = _visible_project_or_404(request.user, project_id)
    summary = project.tasks.aggregate(
        task_count=Count("pk"),
        completed_task_count=Count(
            "pk",
            filter=Q(status=Task.Status.DONE),
        ),
        estimated_effort=Coalesce(
            Sum("estimated_effort"),
            Value(0),
            output_field=EFFORT_FIELD,
        ),
        actual_effort=Coalesce(
            Sum("actual_effort"),
            Value(0),
            output_field=EFFORT_FIELD,
        ),
    )
    completion = (
        round(summary["completed_task_count"] * 100 / summary["task_count"], 2)
        if summary["task_count"]
        else 0
    )
    return _csv_response(
        f"project-{project.pk}-progress.csv",
        [
            "project_id",
            "project_name",
            "status",
            "total_tasks",
            "completed_tasks",
            "completion_percent",
            "estimated_effort_hours",
            "actual_effort_hours",
        ],
        [
            [
                project.pk,
                project.name,
                project.get_status_display(),
                summary["task_count"],
                summary["completed_task_count"],
                completion,
                summary["estimated_effort"],
                summary["actual_effort"],
            ]
        ],
    )


@login_required
@require_GET
def project_velocity_report(request, project_id):
    project = _visible_project_or_404(request.user, project_id)
    sprint_metrics = get_sprint_velocity_metrics(project)["sprints"]
    completed_sprints = [sprint for sprint in sprint_metrics if sprint["is_closed"]]
    return _csv_response(
        f"project-{project.pk}-velocity.csv",
        [
            "sprint_id",
            "sprint_name",
            "start_date",
            "end_date",
            "completed_tasks",
            "completed_tasks_with_estimate",
            "completed_tasks_missing_estimate",
            "known_estimated_effort_hours",
            "velocity_estimated_effort_hours",
            "completed_actual_effort_hours",
        ],
        [
            [
                sprint["sprint"].pk,
                sprint["name"],
                sprint["sprint"].start_date.isoformat(),
                sprint["sprint"].end_date.isoformat(),
                sprint["completed_tasks"],
                sprint["estimated_task_count"],
                sprint["missing_estimate_count"],
                sprint["known_estimated_effort"],
                (
                    sprint["velocity"]
                    if sprint["velocity"] is not None
                    else ""
                ),
                sprint["completed_effort"],
            ]
            for sprint in completed_sprints
        ],
    )


@login_required
@require_GET
def project_workload_report(request, project_id):
    project = _visible_project_or_404(request.user, project_id)
    workload = (
        project.tasks.values(
            "assignee_id",
            "assignee__full_name",
            "assignee__email",
        )
        .annotate(
            task_count=Count("pk"),
            completed_task_count=Count(
                "pk",
                filter=Q(status=Task.Status.DONE),
            ),
            estimated_effort=Coalesce(
                Sum("estimated_effort"),
                Value(0),
                output_field=EFFORT_FIELD,
            ),
            actual_effort=Coalesce(
                Sum("actual_effort"),
                Value(0),
                output_field=EFFORT_FIELD,
            ),
        )
        .order_by("assignee__full_name", "assignee__email")
    )
    return _csv_response(
        f"project-{project.pk}-workload.csv",
        [
            "assignee_id",
            "assignee_name",
            "assignee_email",
            "total_tasks",
            "completed_tasks",
            "estimated_effort_hours",
            "actual_effort_hours",
        ],
        [
            [
                row["assignee_id"] or "",
                row["assignee__full_name"] or (
                    row["assignee__email"] or "Unassigned"
                ),
                row["assignee__email"] or "",
                row["task_count"],
                row["completed_task_count"],
                row["estimated_effort"],
                row["actual_effort"],
            ]
            for row in workload
        ],
    )
