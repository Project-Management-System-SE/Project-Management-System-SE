from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from projects.forms import ProjectMemberForm, ProjectUpdateForm
from projects.models import Project, ProjectMembership


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProjectManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            full_name="System Admin",
            password="admin-safe-password-123",
        )
        self.owner = self.create_user("owner@example.com", "owner", "Project Owner")
        self.manager = self.create_user("manager@example.com", "manager", "Project Manager")
        self.member = self.create_user("member@example.com", "member", "Team Member")
        self.other_manager = self.create_user(
            "other-manager@example.com",
            "other-manager",
            "Other Manager",
        )
        self.inactive_user = self.create_user(
            "inactive@example.com",
            "inactive",
            "Inactive User",
            is_active=False,
        )
        self.outsider = self.create_user(
            "outsider@example.com",
            "outsider",
            "Project Outsider",
        )
        self.project = Project.objects.create(
            name="PMS",
            description="Project description",
            owner=self.owner,
            status=Project.Status.ACTIVE,
            start_date=date(2026, 10, 1),
            due_date=date(2026, 10, 31),
        )
        self.owner_membership = self.add_membership(
            self.owner,
            ProjectMembership.Role.PROJECT_MANAGER,
        )
        self.add_membership(self.manager, ProjectMembership.Role.PROJECT_MANAGER)
        self.add_membership(self.member, ProjectMembership.Role.TEAM_MEMBER)
        self.add_membership(
            self.other_manager,
            ProjectMembership.Role.PROJECT_MANAGER,
        )

    @staticmethod
    def create_user(email, username, full_name, **extra_fields):
        return User.objects.create_user(
            email=email,
            username=username,
            full_name=full_name,
            password="safe-password-123",
            **extra_fields,
        )

    def add_membership(self, user, role):
        return ProjectMembership.objects.create(
            project=self.project,
            user=user,
            project_role=role,
        )

    def edit_payload(self, **overrides):
        payload = {
            "name": "Updated PMS",
            "description": "Updated project description",
            "status": Project.Status.ON_HOLD,
            "start_date": "2026-10-05",
            "due_date": "2026-11-05",
        }
        payload.update(overrides)
        return payload

    def test_project_update_form_accepts_existing_status_values(self):
        form = ProjectUpdateForm(instance=self.project)

        self.assertIn(
            (Project.Status.ON_HOLD, "On Hold"),
            form.fields["status"].choices,
        )
        self.assertIn(
            (Project.Status.ARCHIVED, "Archived"),
            form.fields["status"].choices,
        )

    def test_member_form_limits_choices_to_active_nonmembers(self):
        form = ProjectMemberForm(project=self.project, actor=self.manager)

        choices = list(form.fields["user"].queryset)
        self.assertEqual(choices, [self.outsider])
        self.assertEqual(
            list(form.fields["project_role"].choices),
            [(ProjectMembership.Role.TEAM_MEMBER, "Team Member")],
        )

    def test_admin_can_choose_project_manager_role_for_new_member(self):
        form = ProjectMemberForm(project=self.project, actor=self.admin)

        self.assertEqual(
            list(form.fields["project_role"].choices),
            list(ProjectMembership.Role.choices),
        )

    def test_project_manager_can_update_project_and_list_shows_changes(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("projects:project-update", args=[self.project.pk]),
            self.edit_payload(),
        )

        self.assertRedirects(
            response,
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Updated PMS")
        self.assertEqual(self.project.description, "Updated project description")
        self.assertEqual(self.project.status, Project.Status.ON_HOLD)
        self.assertEqual(self.project.start_date.isoformat(), "2026-10-05")
        self.assertEqual(self.project.due_date.isoformat(), "2026-11-05")
        self.assertEqual(
            ProjectMembership.objects.get(project=self.project, user=self.owner).project_role,
            ProjectMembership.Role.PROJECT_MANAGER,
        )

        list_response = self.client.get(reverse("projects:project-list"))
        detail_response = self.client.get(
            reverse("projects:project-detail", args=[self.project.pk])
        )
        self.assertContains(list_response, "Updated PMS")
        self.assertContains(detail_response, "Updated project description")
        self.assertContains(detail_response, "On Hold")

    def test_admin_can_update_project(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:project-update", args=[self.project.pk]),
            self.edit_payload(name="Admin edit"),
        )

        self.assertRedirects(
            response,
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Admin edit")

    def test_member_and_outsider_cannot_update_project(self):
        for user in (self.member, self.outsider):
            with self.subTest(user=user):
                self.client.force_login(user)
                response = self.client.post(
                    reverse("projects:project-update", args=[self.project.pk]),
                    self.edit_payload(name="Unauthorized edit"),
                )

                self.assertEqual(response.status_code, 403)
                self.project.refresh_from_db()
                self.assertEqual(self.project.name, "PMS")

    def test_project_manager_from_another_project_cannot_update_project(self):
        another_project = Project.objects.create(
            name="Another project",
            owner=self.member,
        )
        ProjectMembership.objects.create(
            project=another_project,
            user=self.outsider,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        self.client.force_login(self.outsider)

        response = self.client.post(
            reverse("projects:project-update", args=[self.project.pk]),
            self.edit_payload(name="Unauthorized edit"),
        )

        self.assertEqual(response.status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "PMS")

    def test_invalid_project_dates_are_rejected_without_saving(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("projects:project-update", args=[self.project.pk]),
            self.edit_payload(
                name="Invalid edit",
                start_date="2026-11-10",
                due_date="2026-11-01",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("due_date", response.context["form"].errors)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "PMS")
        self.assertEqual(self.project.due_date.isoformat(), "2026-10-31")

    def test_owner_can_open_project_detail_and_owner_membership_is_preserved(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("projects:project-detail", args=[self.project.pk])
        )
        remove_response = self.client.post(
            reverse(
                "projects:project-remove-member",
                args=[self.project.pk, self.owner_membership.pk],
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(
            remove_response,
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.assertContains(remove_response, "cannot be removed")
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.owner,
                project_role=ProjectMembership.Role.PROJECT_MANAGER,
            ).exists()
        )

    def test_project_manager_can_add_team_member(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("projects:project-add-member", args=[self.project.pk]),
            {
                "user": self.outsider.pk,
                "project_role": ProjectMembership.Role.TEAM_MEMBER,
            },
        )

        self.assertRedirects(
            response,
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.outsider,
                project_role=ProjectMembership.Role.TEAM_MEMBER,
            ).exists()
        )
        self.assertTrue(User.objects.filter(pk=self.outsider.pk).exists())
        detail_response = self.client.get(
            reverse("projects:project-detail", args=[self.project.pk])
        )
        self.assertContains(detail_response, "Project Outsider")
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.owner,
                project_role=ProjectMembership.Role.PROJECT_MANAGER,
            ).exists()
        )

    def test_duplicate_and_inactive_members_cannot_be_added(self):
        self.client.force_login(self.manager)
        add_url = reverse("projects:project-add-member", args=[self.project.pk])

        duplicate_response = self.client.post(
            add_url,
            {
                "user": self.member.pk,
                "project_role": ProjectMembership.Role.TEAM_MEMBER,
            },
        )
        inactive_response = self.client.post(
            add_url,
            {
                "user": self.inactive_user.pk,
                "project_role": ProjectMembership.Role.TEAM_MEMBER,
            },
        )

        self.assertEqual(duplicate_response.status_code, 200)
        self.assertIn("user", duplicate_response.context["member_form"].errors)
        self.assertEqual(inactive_response.status_code, 200)
        self.assertIn("user", inactive_response.context["member_form"].errors)
        self.assertEqual(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.member,
            ).count(),
            1,
        )

    def test_project_manager_cannot_grant_manager_role(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("projects:project-add-member", args=[self.project.pk]),
            {
                "user": self.outsider.pk,
                "project_role": ProjectMembership.Role.PROJECT_MANAGER,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("project_role", response.context["member_form"].errors)
        self.assertFalse(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.outsider,
            ).exists()
        )

    def test_admin_can_grant_project_manager_role(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:project-add-member", args=[self.project.pk]),
            {
                "user": self.outsider.pk,
                "project_role": ProjectMembership.Role.PROJECT_MANAGER,
            },
        )

        self.assertRedirects(
            response,
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.outsider,
                project_role=ProjectMembership.Role.PROJECT_MANAGER,
            ).exists()
        )

    def test_project_manager_can_remove_team_member_without_deleting_user(self):
        membership = ProjectMembership.objects.get(
            project=self.project,
            user=self.member,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "projects:project-remove-member",
                args=[self.project.pk, membership.pk],
            )
        )

        self.assertRedirects(
            response,
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.assertFalse(ProjectMembership.objects.filter(pk=membership.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())
        detail_response = self.client.get(
            reverse("projects:project-detail", args=[self.project.pk])
        )
        self.assertNotIn(
            self.member,
            [membership.user for membership in detail_response.context["memberships"]],
        )

    def test_project_manager_cannot_remove_another_project_manager(self):
        membership = ProjectMembership.objects.get(
            project=self.project,
            user=self.other_manager,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "projects:project-remove-member",
                args=[self.project.pk, membership.pk],
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(ProjectMembership.objects.filter(pk=membership.pk).exists())

    def test_non_manager_cannot_change_membership(self):
        self.client.force_login(self.member)

        response = self.client.post(
            reverse("projects:project-add-member", args=[self.project.pk]),
            {
                "user": self.outsider.pk,
                "project_role": ProjectMembership.Role.TEAM_MEMBER,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.outsider,
            ).exists()
        )

    def test_project_manager_can_archive_project_but_member_cannot(self):
        archive_url = reverse("projects:project-archive", args=[self.project.pk])
        self.client.force_login(self.member)

        forbidden_response = self.client.post(archive_url)
        self.assertEqual(forbidden_response.status_code, 403)

        self.client.force_login(self.manager)
        response = self.client.post(archive_url)

        self.assertRedirects(
            response,
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ARCHIVED)

    def test_admin_can_archive_and_delete_project(self):
        self.client.force_login(self.admin)

        archive_response = self.client.post(
            reverse("projects:project-archive", args=[self.project.pk])
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ARCHIVED)

        delete_response = self.client.post(
            reverse("projects:project-delete", args=[self.project.pk])
        )

        self.assertEqual(archive_response.status_code, 302)
        self.assertEqual(
            archive_response["Location"],
            reverse("projects:project-detail", args=[self.project.pk]),
        )
        self.assertRedirects(delete_response, reverse("projects:project-list"))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    def test_archive_action_only_accepts_post(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("projects:project-archive", args=[self.project.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ACTIVE)

    def test_project_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        archive_url = reverse("projects:project-archive", args=[self.project.pk])
        client.get(reverse("projects:project-detail", args=[self.project.pk]))

        denied_response = client.post(archive_url)

        self.assertEqual(denied_response.status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ACTIVE)

    def test_delete_requires_confirmation_and_preserves_user_accounts(self):
        delete_url = reverse("projects:project-delete", args=[self.project.pk])
        self.client.force_login(self.manager)

        confirm_response = self.client.get(delete_url)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertContains(confirm_response, "This action cannot be undone.")
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

        response = self.client.post(delete_url)

        self.assertRedirects(response, reverse("projects:project-list"))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(
            ProjectMembership.objects.filter(project_id=self.project.pk).exists()
        )
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())

    def test_member_cannot_delete_project(self):
        self.client.force_login(self.member)

        response = self.client.post(
            reverse("projects:project-delete", args=[self.project.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_anonymous_user_is_redirected_from_project_edit(self):
        response = self.client.get(
            reverse("projects:project-update", args=[self.project.pk])
        )

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('projects:project-update', args=[self.project.pk])}",
        )
