from datetime import date
from unittest.mock import patch

from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from projects.models import Project, ProjectMembership
from tasks.models import Task


def create_user(email, username, full_name):
    return User.objects.create_user(
        email=email,
        username=username,
        full_name=full_name,
        password="safe-password-123",
    )


def project_payload(**overrides):
    payload = {
        "name": "New project",
        "description": "Created by an authorized user",
        "status": Project.Status.PLANNED,
        "start_date": "2026-10-01",
        "due_date": "2026-10-31",
    }
    payload.update(overrides)
    return payload


class DashboardViewTests(TestCase):
    def setUp(self):
        self.owner = create_user("owner@example.com", "owner", "Project Owner")
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="safe-password-123",
        )

    def test_dashboard_supplies_template_context_and_project_details(self):
        active_project = Project.objects.create(
            name="Active project",
            description="Active project description",
            owner=self.owner,
            status=Project.Status.ACTIVE,
            due_date=date(2026, 11, 1),
        )
        ProjectMembership.objects.create(
            project=active_project,
            user=self.owner,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        Project.objects.create(name="Planned project", owner=self.owner)
        Task.objects.create(
            project=active_project,
            title="In progress task",
            created_by=self.owner,
            assignee=self.owner,
        )
        Task.objects.create(
            project=active_project,
            title="Finished task",
            created_by=self.owner,
            assignee=self.owner,
            status=Task.Status.DONE,
        )

        self.client.force_login(self.owner)
        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_projects"], 2)
        self.assertEqual(response.context["active_projects"], 1)
        self.assertEqual(response.context["my_tasks"], 2)
        self.assertEqual(response.context["completed_tasks"], 1)
        self.assertEqual(len(response.context["projects"]), 2)
        self.assertContains(response, 'href="/static/css/style.css"')
        self.assertContains(response, "Active project")
        self.assertContains(response, "Active project description")
        self.assertContains(response, "Active")
        self.assertContains(response, "Nov 1, 2026")
        self.assertContains(response, "Planned project")
        self.assertContains(response, ">50%</span>")
        self.assertContains(response, "No tasks yet")
        self.assertContains(response, 'href="/projects/new/"')
        self.assertContains(response, 'href="/my-tasks/"')

    def test_dashboard_renders_empty_state_for_project_manager(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No projects to show yet")
        self.assertContains(response, "Create your first project")

    def test_dashboard_limits_recent_projects_to_five(self):
        for index in range(6):
            Project.objects.create(name=f"Project {index}", owner=self.owner)

        self.client.force_login(self.owner)
        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["projects"]), 5)

    def test_dashboard_alias_renders(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("projects:dashboard-alias"))

        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('login')}?next={reverse('projects:dashboard')}",
        )

    def test_dashboard_only_counts_visible_projects(self):
        Project.objects.create(name="Visible project", owner=self.owner)
        other_owner = create_user("other@example.com", "other", "Other Owner")
        Project.objects.create(name="Hidden project", owner=other_owner)

        self.client.force_login(self.owner)
        response = self.client.get(reverse("projects:dashboard"))

        self.assertEqual(response.context["total_projects"], 1)
        self.assertEqual(
            [project.name for project in response.context["projects"]],
            ["Visible project"],
        )


class MyTasksViewTests(TestCase):
    def setUp(self):
        self.owner = create_user("owner@example.com", "owner", "Project Owner")
        self.member = create_user("member@example.com", "member", "Team Member")
        self.outsider = create_user("outsider@example.com", "outsider", "Outsider")
        self.project = Project.objects.create(name="Visible project", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.visible_task = Task.objects.create(
            project=self.project,
            title="Assigned task",
            created_by=self.owner,
            assignee=self.member,
        )

    def test_my_tasks_shows_only_assigned_tasks_in_visible_projects(self):
        hidden_project = Project.objects.create(
            name="Hidden project",
            owner=self.outsider,
        )
        Task.objects.create(
            project=hidden_project,
            title="Hidden task",
            created_by=self.outsider,
            assignee=self.member,
        )
        Task.objects.create(
            project=self.project,
            title="Unassigned task",
            created_by=self.owner,
        )

        self.client.force_login(self.member)
        response = self.client.get(reverse("tasks:my-tasks"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["tasks"].values_list("pk", flat=True)),
            [self.visible_task.pk],
        )
        self.assertContains(response, "Assigned task")
        self.assertContains(response, "Visible project")
        self.assertNotContains(response, "Hidden task")
        self.assertContains(
            response,
            reverse(
                "tasks:task-detail",
                kwargs={
                    "project_id": self.project.pk,
                    "task_id": self.visible_task.pk,
                },
            ),
        )

    def test_my_tasks_requires_login(self):
        response = self.client.get(reverse("tasks:my-tasks"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('login')}?next={reverse('tasks:my-tasks')}",
        )


class ProjectVisibilityTests(TestCase):
    def setUp(self):
        self.owner = create_user("owner@example.com", "owner", "Project Owner")
        self.member = create_user("member@example.com", "member", "Team Member")
        self.outsider = create_user("outsider@example.com", "outsider", "Outsider")
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="safe-password-123",
        )
        self.project = Project.objects.create(name="PMS", owner=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )

    def test_project_list_requires_login(self):
        response = self.client.get(reverse("projects:project-list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('login')}?next={reverse('projects:project-list')}",
        )

    def test_owner_sees_owned_project(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("projects:project-list"))

        self.assertIn(self.project, response.context["projects"])

    def test_member_sees_joined_project(self):
        self.client.force_login(self.member)

        response = self.client.get(reverse("projects:project-list"))

        self.assertIn(self.project, response.context["projects"])

    def test_project_list_renders_task_completion_progress(self):
        Task.objects.create(
            project=self.project,
            title="Completed task",
            created_by=self.owner,
            status=Task.Status.DONE,
        )
        Task.objects.create(
            project=self.project,
            title="Open task",
            created_by=self.owner,
        )

        self.client.force_login(self.owner)
        response = self.client.get(reverse("projects:project-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<progress", html=False)
        self.assertContains(response, ">50%</span>")

    def test_admin_sees_all_projects(self):
        other_owner = create_user("other@example.com", "other", "Other Owner")
        other_project = Project.objects.create(name="Other", owner=other_owner)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("projects:project-list"))

        projects = list(response.context["projects"])
        self.assertIn(self.project, projects)
        self.assertIn(other_project, projects)

    def test_unrelated_user_does_not_see_project(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("projects:project-list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.project, response.context["projects"])


class ProjectViewTests(TestCase):
    def setUp(self):
        self.owner = create_user("owner@example.com", "owner", "Project Owner")
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="safe-password-123",
        )

    def test_project_list_supplies_projects(self):
        Project.objects.create(name="PMS", owner=self.owner)

        self.client.force_login(self.owner)
        response = self.client.get(reverse("projects:project-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["projects"]), [Project.objects.get()])
        self.assertContains(response, "PMS")

    def test_project_list_renders_empty_state(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("projects:project-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No projects yet")
        self.assertContains(response, "Create your first project")

    def test_project_list_renders_actual_description_and_status(self):
        Project.objects.create(
            name="Release planning",
            description="Prepare the upcoming release",
            owner=self.owner,
            status=Project.Status.ON_HOLD,
        )

        self.client.force_login(self.owner)
        response = self.client.get(reverse("projects:project-list"))

        self.assertContains(response, "Release planning")
        self.assertContains(response, "Prepare the upcoming release")
        self.assertContains(response, "On Hold")
        self.assertContains(response, "No tasks yet")

    def test_project_search_matches_name_or_description_within_visible_projects(self):
        matching_project = Project.objects.create(
            name="Release planning",
            description="Prepare for the winter launch",
            owner=self.owner,
        )
        hidden_owner = create_user("hidden@example.com", "hidden", "Hidden Owner")
        Project.objects.create(
            name="Hidden release planning",
            description="Secret project",
            owner=hidden_owner,
        )
        self.client.force_login(self.owner)

        name_response = self.client.get(
            reverse("projects:project-list"),
            {"q": "Release planning"},
        )
        description_response = self.client.get(
            reverse("projects:project-list"),
            {"q": "winter launch"},
        )

        self.assertEqual(list(name_response.context["projects"]), [matching_project])
        self.assertEqual(
            list(description_response.context["projects"]),
            [matching_project],
        )
        self.assertNotContains(name_response, "Hidden release planning")

    def test_project_search_empty_results_and_clear_link(self):
        Project.objects.create(name="Available project", owner=self.owner)
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("projects:project-list"),
            {"q": "no matching project"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["projects"]), [])
        self.assertContains(response, "No projects yet")
        self.assertContains(response, "Clear")

    def test_project_list_paginates_filtered_results_and_preserves_search(self):
        for index in range(21):
            Project.objects.create(name=f"Paged project {index}", owner=self.owner)
        self.client.force_login(self.owner)

        first_page = self.client.get(
            reverse("projects:project-list"),
            {"q": "Paged"},
        )
        second_page = self.client.get(
            reverse("projects:project-list"),
            {"q": "Paged", "page": "2"},
        )

        self.assertEqual(first_page.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(first_page.context["projects"]), 20)
        self.assertContains(first_page, "q=Paged&amp;page=2")
        self.assertEqual(len(second_page.context["projects"]), 1)

    def test_project_form_supplies_template_fields(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("projects:project-create"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertEqual(
            list(response.context["project_status_choices"]),
            [
                (Project.Status.PLANNED, "Planned"),
                (Project.Status.ACTIVE, "Active"),
            ],
        )
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'href="/projects/"')
        self.assertContains(response, "Create Project")
        self.assertNotContains(response, "Archived")
        self.assertNotContains(response, " disabled")

    def test_admin_can_create_project_and_becomes_owner(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(status=Project.Status.ACTIVE),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [(reverse("projects:project-list"), 302)])
        self.assertContains(response, "Project created successfully.")
        self.assertContains(response, "New project")
        project = Project.objects.get()
        self.assertEqual(project.owner, self.admin)
        self.assertEqual(project.status, Project.Status.ACTIVE)
        self.assertEqual(
            ProjectMembership.objects.get(project=project, user=self.admin).project_role,
            ProjectMembership.Role.PROJECT_MANAGER,
        )

    def test_anonymous_user_is_redirected_to_login_on_project_creation(self):
        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(name="Anonymous project"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('login')}?next={reverse('projects:project-create')}",
        )
        self.assertFalse(Project.objects.filter(name="Anonymous project").exists())

    def test_project_creation_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        client.get(reverse("projects:project-create"))
        post_data = project_payload(name="CSRF protected project")

        missing_token_response = client.post(
            reverse("projects:project-create"),
            post_data,
        )

        self.assertEqual(missing_token_response.status_code, 403)
        self.assertFalse(
            Project.objects.filter(name="CSRF protected project").exists()
        )

        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("projects:project-create"),
            post_data,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertRedirects(response, reverse("projects:project-list"))
        self.assertTrue(
            Project.objects.filter(
                name="CSRF protected project",
                owner=self.admin,
            ).exists()
        )

    def test_invalid_project_data_is_rejected(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(name=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.exists())
        self.assertIn("name", response.context["form"].errors)
        self.assertContains(response, "This field is required.")
        self.assertContains(response, 'aria-invalid="true"')

    def test_invalid_status_is_rejected_by_project_view(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(name="Invalid status project", status="UNKNOWN"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Project.objects.filter(name="Invalid status project").exists()
        )
        self.assertIn("status", response.context["form"].errors)


class ProjectCreateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="safe-password-123",
        )
        self.existing_pm = create_user(
            "pm@example.com",
            "project-manager",
            "Existing Project Manager",
        )
        self.team_member = create_user(
            "member@example.com",
            "team-member",
            "Team Member",
        )
        self.seed_owner = create_user("seed@example.com", "seed", "Seed Owner")
        seed_project = Project.objects.create(name="Seed project", owner=self.seed_owner)
        ProjectMembership.objects.create(
            project=seed_project,
            user=self.existing_pm,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )

    def test_authorized_get_renders_form_with_limited_statuses(self):
        self.client.force_login(self.existing_pm)

        response = self.client.get(reverse("projects:project-create"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertEqual(
            list(response.context["project_status_choices"]),
            [
                (Project.Status.PLANNED, "Planned"),
                (Project.Status.ACTIVE, "Active"),
            ],
        )

    def test_admin_can_create_project(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(name="Admin project"),
        )

        self.assertRedirects(response, reverse("projects:project-list"))
        project = Project.objects.get(name="Admin project")
        self.assertEqual(project.owner, self.admin)
        membership = ProjectMembership.objects.get(project=project, user=self.admin)
        self.assertEqual(
            membership.project_role,
            ProjectMembership.Role.PROJECT_MANAGER,
        )

    def test_existing_project_manager_can_create_project(self):
        self.client.force_login(self.existing_pm)

        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(name="PM project"),
        )

        self.assertRedirects(response, reverse("projects:project-list"))
        project = Project.objects.get(name="PM project")
        self.assertEqual(project.owner, self.existing_pm)
        membership = ProjectMembership.objects.get(
            project=project,
            user=self.existing_pm,
        )
        self.assertEqual(
            membership.project_role,
            ProjectMembership.Role.PROJECT_MANAGER,
        )

    def test_authenticated_non_manager_cannot_create_project(self):
        self.client.force_login(self.team_member)

        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(name="Unauthorized project"),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Project.objects.filter(name="Unauthorized project").exists())
        self.assertFalse(
            ProjectMembership.objects.filter(user=self.team_member).exists()
        )

    def test_authenticated_non_manager_cannot_open_create_page(self):
        self.client.force_login(self.team_member)

        response = self.client.get(reverse("projects:project-create"))

        self.assertEqual(response.status_code, 403)

    def test_valid_dates_are_persisted(self):
        self.client.force_login(self.admin)

        self.client.post(
            reverse("projects:project-create"),
            project_payload(
                name="Dated project",
                start_date="2026-10-01",
                due_date="2026-10-31",
            ),
        )

        project = Project.objects.get(name="Dated project")
        self.assertEqual(project.start_date.isoformat(), "2026-10-01")
        self.assertEqual(project.due_date.isoformat(), "2026-10-31")

    def test_due_date_before_start_date_is_rejected(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(
                name="Invalid dates",
                start_date="2026-10-10",
                due_date="2026-10-01",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("due_date", response.context["form"].errors)
        self.assertFalse(Project.objects.filter(name="Invalid dates").exists())

    def test_archived_project_cannot_be_created(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:project-create"),
            project_payload(
                name="Archived project",
                status=Project.Status.ARCHIVED,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.context["form"].errors)
        self.assertFalse(Project.objects.filter(name="Archived project").exists())


class ProjectCreateTransactionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="safe-password-123",
        )
        self.client.force_login(self.admin)

    def test_membership_failure_rolls_back_project_creation(self):
        with patch(
            "projects.views.ProjectMembership.objects.create",
            side_effect=IntegrityError("membership creation failed"),
        ):
            with self.assertRaises(IntegrityError):
                self.client.post(
                    reverse("projects:project-create"),
                    project_payload(name="Rollback project"),
                )

        self.assertFalse(Project.objects.filter(name="Rollback project").exists())
        self.assertFalse(
            ProjectMembership.objects.filter(
                project__name="Rollback project"
            ).exists()
        )


class LoginViewTests(TestCase):
    def setUp(self):
        self.email = "login@example.com"
        self.password = "safe-password-123"
        self.user = User.objects.create_user(
            email=self.email,
            username="login-user",
            full_name="Login User",
            password=self.password,
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')

    def test_login_with_email_creates_authenticated_session(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.email, "password": self.password},
        )

        self.assertRedirects(response, reverse("projects:dashboard"))
        self.assertIn("sessionid", response.cookies)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

        dashboard_response = self.client.get(reverse("projects:dashboard"))
        self.assertTrue(dashboard_response.wsgi_request.user.is_authenticated)

    def test_login_rejects_invalid_password(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.email, "password": "incorrect-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct email and password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_ends_authenticated_session(self):
        self.client.post(
            reverse("login"),
            {"username": self.email, "password": self.password},
        )

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        dashboard_response = self.client.get(reverse("projects:dashboard"))
        self.assertRedirects(
            dashboard_response,
            f"{reverse('login')}?next={reverse('projects:dashboard')}",
        )
