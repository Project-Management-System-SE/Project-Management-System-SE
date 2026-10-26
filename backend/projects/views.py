from django.shortcuts import redirect, render

from .forms import ProjectForm
from .models import Project


def dashboard(request):
    projects = Project.objects.select_related("owner").order_by("-created_at")

    context = {
        "total_projects": projects.count(),
        "active_projects": projects.filter(status=Project.Status.ACTIVE).count(),
        "my_tasks": None,
        "completed_tasks": None,
        "projects": projects[:5],
    }
    return render(request, "dashboard.html", context)


def project_list(request):
    projects = Project.objects.select_related("owner").order_by("-created_at")
    return render(request, "projects.html", {"projects": projects})


def project_create(request):
    if request.method == "POST":
        form = ProjectForm(request.POST)
        form_is_valid = form.is_valid()

        if not request.user.is_authenticated:
            form.add_error(None, "You must be signed in to create a project.")
        elif form_is_valid:
            project = form.save(commit=False)
            project.owner = request.user
            project.save()
            return redirect("projects:project-list")
    else:
        form = ProjectForm()

    context = {
        "form": form,
        "project_status_choices": Project.Status.choices,
    }
    return render(request, "project_form.html", context)
