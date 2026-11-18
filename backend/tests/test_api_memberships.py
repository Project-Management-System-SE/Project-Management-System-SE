import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from api.models import APIToken
from projects.models import Project, ProjectMembership


User = get_user_model()


class ProjectMembershipApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="membership_owner",
            email="membership_owner@example.com",
            full_name="Membership Owner",
            password="password123",
        )
        self.manager = User.objects.create_user(
            username="membership_manager",
            email="membership_manager@example.com",
            full_name="Membership Manager",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="membership_member",
            email="membership_member@example.com",
            full_name="Membership Member",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="membership_outsider",
            email="membership_outsider@example.com",
            full_name="Membership Outsider",
            password="password123",
        )
        self.project = Project.objects.create(
            name="Membership API Project",
            owner=self.owner,
            status=Project.Status.ACTIVE,
        )
        self.owner_membership = ProjectMembership.objects.create(
            project=self.project,
            user=self.owner,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        self.manager_membership = ProjectMembership.objects.create(
            project=self.project,
            user=self.manager,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        self.member_membership = ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.owner_token = APIToken.objects.create(user=self.owner)
        self.member_token = APIToken.objects.create(user=self.member)
        self.outsider_token = APIToken.objects.create(user=self.outsider)
        self.url = reverse(
            "api:project-members",
            kwargs={"project_id": self.project.pk},
        )

    def auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token.key}"}

    def test_owner_can_list_and_add_members(self):
        response = self.client.get(self.url, **self.auth(self.owner_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["count"], 3)

        new_user = User.objects.create_user(
            username="membership_new",
            email="membership_new@example.com",
            full_name="Membership New",
            password="password123",
        )
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "user_id": new_user.pk,
                    "role": ProjectMembership.Role.TEAM_MEMBER,
                }
            ),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=new_user,
            ).exists()
        )

    def test_member_and_outsider_cannot_manage_memberships(self):
        member_response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "user_id": self.outsider.pk,
                    "role": ProjectMembership.Role.TEAM_MEMBER,
                }
            ),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        outsider_response = self.client.get(
            self.url,
            **self.auth(self.outsider_token),
        )
        self.assertEqual(member_response.status_code, 403)
        self.assertEqual(outsider_response.status_code, 404)

    def test_owner_can_update_and_remove_member(self):
        detail_url = reverse(
            "api:project-member-detail",
            kwargs={
                "project_id": self.project.pk,
                "membership_id": self.member_membership.pk,
            },
        )
        update_response = self.client.patch(
            detail_url,
            data=json.dumps(
                {"role": ProjectMembership.Role.PROJECT_MANAGER}
            ),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(update_response.status_code, 200)
        self.member_membership.refresh_from_db()
        self.assertEqual(
            self.member_membership.project_role,
            ProjectMembership.Role.PROJECT_MANAGER,
        )

        delete_response = self.client.delete(
            detail_url,
            **self.auth(self.owner_token),
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(
            ProjectMembership.objects.filter(pk=self.member_membership.pk).exists()
        )

    def test_owner_membership_and_invalid_payload_are_protected(self):
        detail_url = reverse(
            "api:project-member-detail",
            kwargs={
                "project_id": self.project.pk,
                "membership_id": self.owner_membership.pk,
            },
        )
        delete_response = self.client.delete(
            detail_url,
            **self.auth(self.owner_token),
        )
        self.assertEqual(delete_response.status_code, 400)

        invalid_response = self.client.post(
            self.url,
            data=json.dumps({"user_id": self.outsider.pk, "role": "INVALID"}),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(invalid_response.status_code, 400)
