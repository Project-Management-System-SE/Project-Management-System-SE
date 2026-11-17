from datetime import timedelta
from decimal import Decimal
from math import ceil

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from tasks.models import Task

from .models import Sprint

EFFORT_FIELD = DecimalField(max_digits=12, decimal_places=2)


def build_sprint_burndown(sprint, today=None):
    today = today or timezone.localdate()
    tasks = sprint.tasks.values_list("estimated_effort", "status", "completed_at")
    total_effort = Decimal("0")
    completed_effort_by_date = {}
    for estimated_effort, status, completed_at in tasks:
        effort = estimated_effort or Decimal("0")
        total_effort += effort
        if status == Task.Status.DONE and completed_at:
            completed_date = timezone.localtime(completed_at).date()
            completed_effort_by_date[completed_date] = (
                completed_effort_by_date.get(completed_date, Decimal("0")) + effort
            )

    start_date = sprint.start_date
    end_date = sprint.end_date
    current_date = min(max(today, start_date), end_date)
    span_days = max((end_date - start_date).days, 1)
    observed_days = (current_date - start_date).days
    stride = max(1, ceil(span_days / 60))
    offsets = list(range(0, observed_days + 1, stride))
    if not offsets or offsets[-1] != observed_days:
        offsets.append(observed_days)

    completed_effort = Decimal("0")
    completion_events = sorted(completed_effort_by_date.items())
    completion_event_index = 0
    points = []
    for offset in offsets:
        point_date = start_date + timedelta(days=offset)
        while (
            completion_event_index < len(completion_events)
            and completion_events[completion_event_index][0] <= point_date
        ):
            completed_effort += completion_events[completion_event_index][1]
            completion_event_index += 1
        remaining_effort = max(total_effort - completed_effort, Decimal("0"))
        ideal_remaining = total_effort * Decimal(span_days - offset) / Decimal(span_days)
        x = 10 + (280 * offset / span_days)
        if total_effort:
            ideal_y = 10 + (90 * (total_effort - ideal_remaining) / total_effort)
            actual_y = 10 + (90 * (total_effort - remaining_effort) / total_effort)
        else:
            ideal_y = actual_y = 100
        points.append(
            {
                "ideal": f"{x:.2f},{ideal_y:.2f}",
                "actual": f"{x:.2f},{actual_y:.2f}",
                "remaining_effort": remaining_effort,
            }
        )

    return {
        "has_estimates": bool(total_effort),
        "total_effort": total_effort,
        "current_remaining_effort": points[-1]["remaining_effort"],
        "ideal_points": " ".join(point["ideal"] for point in points),
        "actual_points": " ".join(point["actual"] for point in points),
        "start_label": start_date.strftime("%b %d"),
        "current_label": current_date.strftime("%b %d"),
        "end_label": end_date.strftime("%b %d"),
    }


def completed_sprint_metrics(project):
    return project.sprints.filter(status=Sprint.Status.COMPLETED).annotate(
        completed_task_count=Count(
            "tasks",
            filter=Q(tasks__status=Task.Status.DONE),
        ),
        velocity_effort=Coalesce(
            Sum(
                "tasks__estimated_effort",
                filter=Q(tasks__status=Task.Status.DONE),
            ),
            Value(Decimal("0")),
            output_field=EFFORT_FIELD,
        ),
        completed_actual_effort=Coalesce(
            Sum(
                "tasks__actual_effort",
                filter=Q(tasks__status=Task.Status.DONE),
            ),
            Value(Decimal("0")),
            output_field=EFFORT_FIELD,
        ),
    ).order_by("end_date", "pk")
