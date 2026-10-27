from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import ProjectForm
from .models import Project, ProjectMembership
from .permissions import can_create_project, visible_projects_for


@login_required
def dashboard(request):
    projects = visible_projects_for(request.user)

    context = {
        "total_projects": projects.count(),
        "active_projects": projects.filter(status=Project.Status.ACTIVE).count(),
        "my_tasks": None,
        "completed_tasks": None,
        "projects": projects[:5],
        "can_create_project": can_create_project(request.user),
    }
    return render(request, "dashboard.html", context)


@login_required
def project_list(request):
    projects = visible_projects_for(request.user)
    context = {
        "projects": projects,
        "can_create_project": can_create_project(request.user),
    }
    return render(request, "projects.html", context)


@login_required
def project_create(request):
    if not can_create_project(request.user):
        raise PermissionDenied

    if request.method == "POST":
        form = ProjectForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                project = form.save(commit=False)
                project.owner = request.user
                project.save()
                ProjectMembership.objects.create(
                    project=project,
                    user=request.user,
                    project_role=ProjectMembership.Role.PROJECT_MANAGER,
                )

            messages.success(request, "Project created successfully.")
            return redirect("projects:project-list")
    else:
        form = ProjectForm()

    context = {
        "form": form,
        "project_status_choices": form.fields["status"].choices,
    }
    return render(request, "project_form.html", context)
