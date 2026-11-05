from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from projects.models import Project, ProjectMembership, Sprint
from tasks.admin import AuditLogAdmin
from tasks.models import AuditLog, Task


class AuditLogTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="test-pass-123",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Team Member",
            password="test-pass-123",
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com",
            username="outsider",
            full_name="Outsider",
            password="test-pass-123",
        )
        self.project = Project.objects.create(name="Audit project", owner=self.owner)
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
        self.client.force_login(self.owner)

    def test_project_create_update_and_delete_are_recorded_and_retained(self):
        response = self.client.post(
            reverse("projects:project-create"),
            {"name": "Created project", "description": "", "status": "PLANNED"},
        )
        created_project = Project.objects.get(name="Created project")
        self.assertEqual(response.status_code, 302)
        create_entry = AuditLog.objects.get(
            object_id=created_project.pk,
            action=AuditLog.Action.CREATE,
        )
        self.assertEqual(create_entry.actor, self.owner)
        self.assertIsNotNone(create_entry.timestamp)

        self.client.post(
            reverse("projects:project-update", args=[created_project.pk]),
            {
                "name": "Renamed project",
                "description": "",
                "status": "ACTIVE",
                "start_date": "",
                "due_date": "",
            },
        )
        update_entry = AuditLog.objects.get(
            object_id=created_project.pk,
            action=AuditLog.Action.UPDATE,
        )
        self.assertEqual(update_entry.changes["name"]["to"], "Renamed project")
        self.assertNotIn("description", update_entry.changes)

        self.client.post(reverse("projects:project-delete", args=[created_project.pk]))
        delete_entry = AuditLog.objects.get(
            object_id=created_project.pk,
            action=AuditLog.Action.DELETE,
        )
        self.assertIsNone(delete_entry.project_id)
        self.assertEqual(delete_entry.project_id_snapshot, created_project.pk)
        self.assertEqual(delete_entry.object_name, "Renamed project")

    def test_task_create_update_and_delete_are_recorded_and_retained(self):
        response = self.client.post(
            reverse("tasks:task-create", args=[self.project.pk]),
            {
                "title": "Audit task",
                "description": "",
                "priority": "MEDIUM",
                "status": "TODO",
                "due_date": "",
                "estimated_effort": "",
                "actual_effort": "",
                "sprint": "",
                "milestone": "",
                "assignee": "",
                "labels": "",
            },
        )
        task = Task.objects.get(title="Audit task")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AuditLog.objects.filter(
                task=task,
                action=AuditLog.Action.CREATE,
                actor=self.owner,
            ).exists()
        )

        self.client.post(
            reverse("tasks:task-update", args=[self.project.pk, task.pk]),
            {
                "title": "Updated audit task",
                "description": "Changed",
                "priority": "HIGH",
                "status": "TODO",
                "due_date": "",
                "estimated_effort": "",
                "actual_effort": "",
                "sprint": "",
                "milestone": "",
                "assignee": "",
                "labels": "",
            },
        )
        update_entry = AuditLog.objects.get(
            task=task,
            action=AuditLog.Action.UPDATE,
        )
        self.assertEqual(update_entry.changes["title"]["to"], "Updated audit task")
        self.assertEqual(update_entry.changes["priority"]["from"], "MEDIUM")

        self.client.post(reverse("tasks:task-delete", args=[self.project.pk, task.pk]))
        delete_entry = AuditLog.objects.get(
            object_id=task.pk,
            action=AuditLog.Action.DELETE,
        )
        self.assertIsNone(delete_entry.task_id)
        self.assertEqual(delete_entry.project_id, self.project.pk)
        self.assertEqual(delete_entry.project_id_snapshot, self.project.pk)
        self.assertEqual(delete_entry.object_name, "Updated audit task")

    def test_sprint_closure_logs_carry_over_updates(self):
        sprint = Sprint.objects.create(
            project=self.project,
            name="Active sprint",
            start_date="2026-11-01",
            end_date="2026-11-14",
            status=Sprint.Status.ACTIVE,
        )
        destination = Sprint.objects.create(
            project=self.project,
            name="Next sprint",
            start_date="2026-11-15",
            end_date="2026-11-28",
        )
        backlog_task = Task.objects.create(
            project=self.project,
            title="Backlog task",
            created_by=self.owner,
            sprint=sprint,
        )
        carried_task = Task.objects.create(
            project=self.project,
            title="Carried task",
            created_by=self.owner,
            sprint=sprint,
        )

        self.client.post(
            reverse("projects:sprint-close", args=[self.project.pk, sprint.pk]),
            {"carry_over_sprint": destination.pk, "note": "Carry forward"},
        )

        updates = AuditLog.objects.filter(
            object_type=AuditLog.ObjectType.TASK,
            action=AuditLog.Action.UPDATE,
        )
        self.assertEqual(updates.count(), 2)
        for task in (backlog_task, carried_task):
            entry = updates.get(object_id=task.pk)
            self.assertEqual(entry.actor, self.owner)
            self.assertEqual(entry.changes["sprint"]["from"], sprint.pk)
        self.assertEqual(
            updates.get(object_id=backlog_task.pk).changes["sprint"]["to"],
            destination.pk,
        )

    def test_task_status_update_is_audited(self):
        task = Task.objects.create(
            project=self.project,
            title="Status task",
            created_by=self.owner,
        )
        self.client.post(
            reverse(
                "tasks:task-update-status",
                args=[self.project.pk, task.pk],
            ),
            {"status": Task.Status.IN_PROGRESS},
        )
        entry = AuditLog.objects.get(
            object_id=task.pk,
            action=AuditLog.Action.UPDATE,
        )
        self.assertEqual(entry.changes["status"]["from"], Task.Status.TODO)
        self.assertEqual(entry.changes["status"]["to"], Task.Status.IN_PROGRESS)

    def test_deleted_project_history_is_authorized_by_retained_snapshot(self):
        task = Task.objects.create(
            project=self.project,
            title="Retained task",
            created_by=self.owner,
        )
        from tasks.audit import record_audit

        record_audit(self.owner, AuditLog.Action.CREATE, task)
        project_id = self.project.pk
        self.client.post(reverse("projects:project-delete", args=[project_id]))

        response = self.client.get(
            reverse("projects:project-activity", args=[project_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(entry.object_name == "Retained task" for entry in response.context["activity"])
        )
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(
                reverse("projects:project-activity", args=[project_id])
            ).status_code,
            404,
        )

    def test_deleted_actor_keeps_actor_snapshot(self):
        from tasks.audit import record_audit

        record_audit(self.member, AuditLog.Action.CREATE, self.project)
        entry = AuditLog.objects.latest("pk")
        self.member.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.actor_id)
        self.assertEqual(entry.actor_name, "Team Member")

    def test_activity_is_newest_first_and_project_scoped(self):
        older = AuditLog.objects.create(
            actor=self.owner,
            actor_name=self.owner.full_name,
            action=AuditLog.Action.CREATE,
            object_type=AuditLog.ObjectType.PROJECT,
            object_id=self.project.pk,
            object_name=self.project.name,
            project_id_snapshot=self.project.pk,
            project=self.project,
            project_name=self.project.name,
            authorized_user_ids=[self.owner.pk, self.member.pk],
            description="Older event",
        )
        newer = AuditLog.objects.create(
            actor=self.owner,
            actor_name=self.owner.full_name,
            action=AuditLog.Action.UPDATE,
            object_type=AuditLog.ObjectType.PROJECT,
            object_id=self.project.pk,
            object_name=self.project.name,
            project_id_snapshot=self.project.pk,
            project=self.project,
            project_name=self.project.name,
            authorized_user_ids=[self.owner.pk, self.member.pk],
            description="Newer event",
        )
        response = self.client.get(
            reverse("projects:project-activity", args=[self.project.pk])
        )
        self.assertEqual(list(response.context["activity"]), [newer, older])

    def test_activity_requires_project_access_and_login(self):
        self.client.logout()
        response = self.client.get(
            reverse("projects:project-activity", args=[self.project.pk])
        )
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('projects:project-activity', args=[self.project.pk])}",
        )

        self.client.force_login(self.outsider)
        response = self.client.get(
            reverse("projects:project-activity", args=[self.project.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_audit_entries_are_immutable(self):
        entry = AuditLog.objects.create(
            actor=self.owner,
            actor_name=self.owner.full_name,
            action=AuditLog.Action.CREATE,
            object_type=AuditLog.ObjectType.PROJECT,
            object_id=self.project.pk,
            object_name=self.project.name,
            project_id_snapshot=self.project.pk,
            project=self.project,
            project_name=self.project.name,
            authorized_user_ids=[self.owner.pk],
            description="Immutable event",
        )
        entry.description = "Changed"
        with self.assertRaises(PermissionDenied):
            entry.save()
        with self.assertRaises(PermissionDenied):
            entry.delete()
        with self.assertRaises(PermissionDenied):
            AuditLog.objects.filter(pk=entry.pk).update(description="Changed")
        with self.assertRaises(PermissionDenied):
            AuditLog.objects.filter(pk=entry.pk).delete()
        with self.assertRaises(PermissionDenied):
            AuditLog.objects.bulk_update([entry], ["description"])
        with self.assertRaises(PermissionDenied):
            AuditLog.objects.bulk_create([entry])

    def test_admin_cannot_delete_audit_entries_individually_or_in_bulk(self):
        admin = AuditLogAdmin(AuditLog, None)
        self.assertFalse(admin.has_delete_permission(None))
        with self.assertRaises(PermissionDenied):
            admin.delete_queryset(None, AuditLog.objects.none())

    def test_failed_operations_do_not_create_audit_entries(self):
        before = AuditLog.objects.count()
        response = self.client.post(
            reverse("projects:project-update", args=[self.project.pk]),
            {
                "name": "",
                "description": "",
                "status": "ACTIVE",
                "start_date": "",
                "due_date": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AuditLog.objects.count(), before)
