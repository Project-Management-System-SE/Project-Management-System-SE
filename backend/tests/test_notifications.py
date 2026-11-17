from datetime import timedelta

from django.contrib import admin
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from projects.models import Project, ProjectMembership
from tasks.admin import TaskAdmin
from tasks.models import Task, TaskComment, TaskDueReminder, UserNotification


class NotificationTests(TestCase):
    def setUp(self):
        self.manager = self.create_user("manager@example.com", "Manager")
        self.creator = self.create_user("creator@example.com", "Creator")
        self.assignee = self.create_user("assignee@example.com", "Assignee")
        self.new_assignee = self.create_user("new@example.com", "New Assignee")
        self.project = Project.objects.create(
            name="Notifications Project",
            owner=self.manager,
        )
        self.add_member(self.manager, ProjectMembership.Role.PROJECT_MANAGER)
        self.add_member(self.creator, ProjectMembership.Role.TEAM_MEMBER)
        self.add_member(self.assignee, ProjectMembership.Role.TEAM_MEMBER)
        self.add_member(self.new_assignee, ProjectMembership.Role.TEAM_MEMBER)
        self.task = Task.objects.create(
            project=self.project,
            title="Prepare release",
            created_by=self.creator,
            assignee=self.assignee,
        )

    @staticmethod
    def create_user(email, full_name):
        return User.objects.create_user(
            email=email,
            username=email.partition("@")[0],
            full_name=full_name,
            password="safe-test-password-123!",
        )

    def add_member(self, user, role):
        return ProjectMembership.objects.create(
            project=self.project,
            user=user,
            project_role=role,
        )

    def notifications_for(self, user):
        return UserNotification.objects.filter(recipient=user)

    def test_project_member_addition_creates_notification_for_affected_user(self):
        new_user = self.create_user("added@example.com", "Added User")
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("projects:project-add-member", args=[self.project.pk]),
            {
                "user": new_user.pk,
                "project_role": ProjectMembership.Role.TEAM_MEMBER,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=new_user,
            ).exists()
        )
        notification = self.notifications_for(new_user).get()
        self.assertEqual(notification.title, f"Added to project: {self.project.name}")
        self.assertIn("added to the project", notification.message)
        self.assertFalse(notification.is_read)

    def test_project_member_removal_creates_notification_for_affected_user(self):
        membership = ProjectMembership.objects.get(
            project=self.project,
            user=self.assignee,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "projects:project-remove-member",
                args=[self.project.pk, membership.pk],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProjectMembership.objects.filter(pk=membership.pk).exists())
        notification = self.notifications_for(self.assignee).get()
        self.assertEqual(notification.title, f"Removed from project: {self.project.name}")
        self.assertIn("membership", notification.message)

    def test_task_assignment_creates_notifications_on_creation_and_reassignment(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("tasks:task-create", args=[self.project.pk]),
            {
                "title": "New assigned task",
                "description": "",
                "priority": Task.Priority.MEDIUM,
                "due_date": "",
                "assignee": self.assignee.pk,
                "status": Task.Status.TODO,
                "labels": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.notifications_for(self.assignee).count(),
            1,
        )
        self.assertIn(
            "New assigned task",
            self.notifications_for(self.assignee).get().title,
        )

        response = self.client.post(
            reverse("tasks:task-update", args=[self.project.pk, self.task.pk]),
            {
                "title": self.task.title,
                "description": self.task.description,
                "priority": self.task.priority,
                "due_date": "",
                "assignee": self.new_assignee.pk,
                "status": self.task.status,
                "labels": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.assignee, self.new_assignee)
        self.assertEqual(self.notifications_for(self.new_assignee).count(), 1)

    def test_task_status_change_notifies_assignee_and_creator_not_actor(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "tasks:task-update-status",
                args=[self.project.pk, self.task.pk],
            ),
            {"status": Task.Status.IN_PROGRESS},
        )

        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(self.notifications_for(self.assignee).count(), 1)
        self.assertEqual(self.notifications_for(self.creator).count(), 1)
        self.assertEqual(self.notifications_for(self.manager).count(), 0)
        self.assertIn(
            "In Progress",
            self.notifications_for(self.assignee).get().message,
        )

    def test_unchanged_task_status_does_not_create_notification(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "tasks:task-update-status",
                args=[self.project.pk, self.task.pk],
            ),
            {"status": self.task.status},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(UserNotification.objects.count(), 0)

    def test_admin_task_assignment_and_status_changes_create_notifications(self):
        request = RequestFactory().post("/admin/tasks/task/")
        request.user = self.manager
        task = Task.objects.get(pk=self.task.pk)
        task.assignee = self.new_assignee
        task.status = Task.Status.IN_PROGRESS

        TaskAdmin(Task, admin.site).save_model(
            request,
            task,
            form=None,
            change=True,
        )

        notifications = list(UserNotification.objects.order_by("recipient_id", "pk"))
        self.assertEqual(
            {(notification.title, notification.recipient.email) for notification in notifications},
            {
                (f"Task assigned to you: {self.task.title}", self.new_assignee.email),
                (f"Task status changed: {self.task.title}", self.new_assignee.email),
                (f"Task status changed: {self.task.title}", self.creator.email),
            },
        )

    def test_comment_is_saved_displayed_and_notifies_other_task_participants(self):
        self.client.force_login(self.creator)
        response = self.client.post(
            reverse(
                "tasks:task-add-comment",
                args=[self.project.pk, self.task.pk],
            ),
            {"content": "Release notes are ready."},
        )

        self.assertEqual(response.status_code, 302)
        comment = TaskComment.objects.get(task=self.task)
        self.assertEqual(comment.author, self.creator)
        notification = self.notifications_for(self.assignee).get()
        self.assertEqual(notification.title, f"New comment on task: {self.task.title}")
        self.assertIn("Release notes are ready.", notification.message)
        self.assertEqual(self.notifications_for(self.creator).count(), 0)

        detail_response = self.client.get(
            reverse("tasks:task-detail", args=[self.project.pk, self.task.pk])
        )
        self.assertContains(detail_response, "Release notes are ready.")
        self.assertContains(detail_response, "Post comment")

    def test_due_date_command_creates_one_in_app_reminder_for_tomorrow(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.task.due_date = tomorrow
        self.task.save()
        completed_task = Task.objects.create(
            project=self.project,
            title="Already complete",
            created_by=self.creator,
            assignee=self.assignee,
            status=Task.Status.DONE,
            due_date=tomorrow,
        )

        call_command("send_due_date_reminders")
        call_command("send_due_date_reminders")

        notification = self.notifications_for(self.assignee).get()
        self.assertEqual(notification.title, f"Task due tomorrow: {self.task.title}")
        self.assertTrue(
            TaskDueReminder.objects.filter(
                task=self.task,
                due_date=tomorrow,
            ).exists()
        )
        self.assertFalse(
            TaskDueReminder.objects.filter(task=completed_task).exists()
        )

    def test_notification_inbox_only_shows_signed_in_users_notifications(self):
        own_notification = UserNotification.objects.create(
            recipient=self.assignee,
            title="Your task changed",
            message="The task status changed.",
        )
        UserNotification.objects.create(
            recipient=self.creator,
            title="Private notification",
            message="Only for the creator.",
        )
        self.client.force_login(self.assignee)

        response = self.client.get(reverse("tasks:notification-inbox"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your task changed")
        self.assertNotContains(response, "Private notification")
        self.assertContains(response, "1 unread notification")
        self.assertContains(response, reverse("tasks:notification-mark-read", args=[own_notification.pk]))

    def test_user_can_mark_own_notification_read_but_not_another_users(self):
        own_notification = UserNotification.objects.create(
            recipient=self.assignee,
            title="Own notification",
            message="Own message.",
        )
        other_notification = UserNotification.objects.create(
            recipient=self.creator,
            title="Other notification",
            message="Private message.",
        )
        self.client.force_login(self.assignee)

        response = self.client.post(
            reverse("tasks:notification-mark-read", args=[own_notification.pk])
        )

        self.assertRedirects(response, reverse("tasks:notification-inbox"))
        own_notification.refresh_from_db()
        self.assertTrue(own_notification.is_read)
        self.assertEqual(
            self.client.post(
                reverse("tasks:notification-mark-read", args=[other_notification.pk])
            ).status_code,
            404,
        )
        other_notification.refresh_from_db()
        self.assertFalse(other_notification.is_read)
