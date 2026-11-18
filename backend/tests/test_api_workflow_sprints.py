import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from api.models import APIToken
from projects.models import Project, ProjectMembership, Sprint, Milestone


User = get_user_model()


class WorkflowAndPlanningApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="planning_owner",
            email="planning_owner@example.com",
            full_name="Planning Owner",
            password="password123",
        )
        self.member = User.objects.create_user(
            username="planning_member",
            email="planning_member@example.com",
            full_name="Planning Member",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="planning_outsider",
            email="planning_outsider@example.com",
            full_name="Planning Outsider",
            password="password123",
        )
        self.project = Project.objects.create(
            name="Planning API Project",
            owner=self.owner,
            status=Project.Status.ACTIVE,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.owner,
            project_role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.owner_token = APIToken.objects.create(user=self.owner)
        self.member_token = APIToken.objects.create(user=self.member)
        self.outsider_token = APIToken.objects.create(user=self.outsider)

    def auth(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token.key}"}

    def test_workflow_get_update_and_review_rule(self):
        url = reverse("api:project-workflow", kwargs={"project_id": self.project.pk})
        response = self.client.get(url, **self.auth(self.owner_token))
        self.assertEqual(response.status_code, 200)

        update_url = reverse(
            "api:project-workflow-update",
            kwargs={"project_id": self.project.pk},
        )
        payload = {
            "states": ["Open", "In Development", "QA", "Released"],
            "initial_state": "Open",
            "final_state": "Released",
            "transitions": [
                {"from": "Open", "to": "In Development"},
                {"from": "In Development", "to": "QA"},
                {"from": "QA", "to": "Released"},
            ],
        }
        response = self.client.put(
            update_url,
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.project.workflow_states.filter(is_final=True).exists())

        bypass = dict(payload)
        bypass["states"] = ["Open", "In Development", "Released"]
        bypass["initial_state"] = "Open"
        bypass["final_state"] = "Released"
        bypass["transitions"] = [
            {"from": "Open", "to": "In Development"},
            {"from": "In Development", "to": "Released"},
        ]
        response = self.client.put(
            update_url,
            data=json.dumps(bypass),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(response.status_code, 400)

    def test_workflow_update_requires_manager(self):
        url = reverse(
            "api:project-workflow-update",
            kwargs={"project_id": self.project.pk},
        )
        payload = {
            "states": ["Open", "QA", "Done"],
            "initial_state": "Open",
            "final_state": "Done",
            "transitions": [{"from": "QA", "to": "Done"}],
        }
        response = self.client.put(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **self.auth(self.member_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_sprint_crud_and_cross_project_access(self):
        list_url = reverse(
            "api:project-sprints",
            kwargs={"project_id": self.project.pk},
        )
        create_response = self.client.post(
            list_url,
            data=json.dumps({
                "name": "API Sprint",
                "goal": "Ship API",
                "start_date": "2026-11-01",
                "end_date": "2026-11-15",
            }),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(create_response.status_code, 201)
        sprint = Sprint.objects.get(name="API Sprint")

        detail_url = reverse(
            "api:project-sprint-detail",
            kwargs={"project_id": self.project.pk, "sprint_id": sprint.pk},
        )
        patch_response = self.client.patch(
            detail_url,
            data=json.dumps({"goal": "Updated goal", "status": "ACTIVE"}),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(patch_response.status_code, 200)

        outsider_url = reverse(
            "api:project-sprint-detail",
            kwargs={"project_id": self.project.pk, "sprint_id": sprint.pk},
        )
        outsider_response = self.client.get(
            outsider_url,
            **self.auth(self.outsider_token),
        )
        self.assertEqual(outsider_response.status_code, 404)

    def test_milestone_crud_and_permission(self):
        list_url = reverse(
            "api:project-milestones",
            kwargs={"project_id": self.project.pk},
        )
        create_response = self.client.post(
            list_url,
            data=json.dumps({
                "name": "API Milestone",
                "description": "Release milestone",
                "target_date": "2026-12-01",
            }),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(create_response.status_code, 201)
        milestone = Milestone.objects.get(name="API Milestone")

        detail_url = reverse(
            "api:project-milestone-detail",
            kwargs={"project_id": self.project.pk, "milestone_id": milestone.pk},
        )
        patch_response = self.client.patch(
            detail_url,
            data=json.dumps({"status": "IN_PROGRESS"}),
            content_type="application/json",
            **self.auth(self.owner_token),
        )
        self.assertEqual(patch_response.status_code, 200)
        delete_response = self.client.delete(
            detail_url,
            **self.auth(self.owner_token),
        )
        self.assertEqual(delete_response.status_code, 200)
