import csv
import io

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from tasks.models import Task

from .analytics import completed_sprint_metrics
from .models import Project
from .permissions import visible_projects_for

EFFORT_FIELD = DecimalField(max_digits=12, decimal_places=2)


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
    sprints = completed_sprint_metrics(project)
    return _csv_response(
        f"project-{project.pk}-velocity.csv",
        [
            "sprint_id",
            "sprint_name",
            "start_date",
            "end_date",
            "completed_tasks",
            "velocity_estimated_effort_hours",
            "completed_actual_effort_hours",
        ],
        [
            [
                sprint.pk,
                sprint.name,
                sprint.start_date.isoformat(),
                sprint.end_date.isoformat(),
                sprint.completed_task_count,
                sprint.velocity_effort,
                sprint.completed_actual_effort,
            ]
            for sprint in sprints
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
