import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from projects.models import Project, Sprint, Milestone
from projects.permissions import visible_projects_for, can_manage_project
from projects.workflow import is_valid_transition
from tasks.models import Task
from tasks.permissions import (
    can_view_tasks_for,
    can_create_task_in,
    can_edit_task,
    can_delete_task,
    can_reassign_task,
)
from .auth import api_auth_required
from .helpers import (
    error_response,
    serialize_project,
    serialize_task,
    success_response,
)


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def project_list_api(request):
    projects = visible_projects_for(request.user).select_related("owner")
    data = [serialize_project(p) for p in projects]
    return success_response({"projects": data, "count": len(data)})


@csrf_exempt
@api_auth_required
@require_http_methods(["GET"])
def project_detail_api(request, project_id):
    try:
        project = visible_projects_for(request.user).select_related("owner").get(pk=project_id)
    except Project.DoesNotExist:
        return error_response("Project not found or access denied.", status=404)

    return success_response(serialize_project(project))
