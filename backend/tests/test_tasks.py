import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from projects.models import Project, ProjectMembership
from tasks.forms import TaskForm
from tasks.models import Task, TaskAttachment, TaskComment, TaskLabel

User = get_user_model()


class TaskBackendModelAndLabelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="testpassword123",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Team Member",
            password="testpassword123",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            username="other",
            full_name="Other User",
            password="testpassword123",
        )
        self.project = Project.objects.create(
            name="Alpha Project",
            description="Alpha description",
            owner=self.owner,
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

    def test_task_creation_with_defaults(self):
        task = Task.objects.create(
            project=self.project,
            title="Setup database",
            created_by=self.owner,
        )
        self.assertEqual(task.priority, Task.Priority.MEDIUM)
        self.assertEqual(task.status, Task.Status.TODO)
        self.assertIsNone(task.assignee)
        self.assertIsNone(task.due_date)
        self.assertIn("Setup database", str(task))

    def test_task_assignee_validation_must_be_project_member(self):
        task = Task(
            project=self.project,
            title="Invalid assignee task",
            created_by=self.owner,
            assignee=self.other_user,
        )
        with self.assertRaises(ValidationError):
            task.clean()

    def test_labels_project_scoping_and_normalization(self):
        label1 = TaskLabel.objects.create(
            project=self.project,
            name="  Urgent  ",
        )
        self.assertEqual(label1.name, "urgent")

        # Duplicate name in same project raises IntegrityError
        from django.db import IntegrityError, transaction

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                TaskLabel.objects.create(
                    project=self.project,
                    name="urgent",
                )

        # Same label name in a different project is allowed
        project_b = Project.objects.create(
            name="Beta Project",
            owner=self.owner,
        )
        label_b = TaskLabel.objects.create(
            project=project_b,
            name="urgent",
        )
        self.assertEqual(label_b.project, project_b)

    def test_task_labels_persistence_and_update(self):
        task = Task.objects.create(
            project=self.project,
            title="Feature implementation",
            created_by=self.owner,
        )
        label1 = TaskLabel.objects.create(project=self.project, name="frontend")
        label2 = TaskLabel.objects.create(project=self.project, name="ui")

        task.labels.add(label1, label2)
        self.assertEqual(task.labels.count(), 2)
        self.assertIn("frontend", task.get_labels_as_string())

        # Update labels: remove ui, add accessibility
        label3 = TaskLabel.objects.create(project=self.project, name="accessibility")
        task.labels.set([label1, label3])
        self.assertEqual(task.labels.count(), 2)
        self.assertNotIn("ui", task.get_labels_as_string())
        self.assertIn("accessibility", task.get_labels_as_string())


class TaskFormTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            full_name="Project Owner",
            password="testpassword123",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Team Member",
            password="testpassword123",
        )
        self.unrelated_user = User.objects.create_user(
            email="unrelated@example.com",
            username="unrelated",
            full_name="Unrelated User",
            password="testpassword123",
        )
        self.project = Project.objects.create(
            name="Project Gamma",
            owner=self.owner,
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

    def test_valid_task_form_submission(self):
        form = TaskForm(
            data={
                "title": "Write unit tests",
                "description": "Ensure 100% test coverage.",
                "priority": "HIGH",
                "due_date": "2026-12-31",
                "assignee": str(self.member.pk),
                "status": "IN_PROGRESS",
                "labels": "testing, Quality, Backend",
            },
            project=self.project,
        )
        self.assertTrue(form.is_valid(), form.errors)
        task = form.save(commit=False)
        task.created_by = self.owner
        task.save()
        form.save_m2m()

        self.assertEqual(task.title, "Write unit tests")
        self.assertEqual(task.assignee, self.member)
        self.assertEqual(task.priority, Task.Priority.HIGH)
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(task.labels.count(), 3)
        self.assertEqual(
            set(task.labels.values_list("name", flat=True)),
            {"testing", "quality", "backend"},
        )

    def test_missing_required_title(self):
        form = TaskForm(
            data={
                "title": "",
                "priority": "LOW",
                "status": "TODO",
            },
            project=self.project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_invalid_assignee_not_in_project(self):
        form = TaskForm(
            data={
                "title": "Check assignee",
                "priority": "LOW",
                "status": "TODO",
                "assignee": str(self.unrelated_user.pk),
            },
            project=self.project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("assignee", form.errors)

    def test_labels_deduplication_trimming_and_max_length(self):
        # Trimming and deduplication
        form = TaskForm(
            data={
                "title": "Task with repeated labels",
                "priority": "LOW",
                "status": "TODO",
                "labels": "bug, BUG,  bug  , critical",
            },
            project=self.project,
        )
        self.assertTrue(form.is_valid())
        cleaned_labels = form.cleaned_data["labels"]
        self.assertEqual(cleaned_labels, ["bug", "critical"])

        # Label too long (> 50 chars)
        long_label = "a" * 51
        form_long = TaskForm(
            data={
                "title": "Too long label",
                "priority": "LOW",
                "status": "TODO",
                "labels": f"valid, {long_label}",
            },
            project=self.project,
        )
        self.assertFalse(form_long.is_valid())
        self.assertIn("labels", form_long.errors)

    def test_edit_preserves_and_updates_labels(self):
        task = Task.objects.create(
            project=self.project,
            title="Initial Task",
            created_by=self.owner,
        )
        label1 = TaskLabel.objects.create(project=self.project, name="v1")
        label2 = TaskLabel.objects.create(project=self.project, name="feature")
        task.labels.add(label1, label2)

        # Initialize form with instance in GET mode
        form = TaskForm(instance=task)
        initial_labels = {x.strip() for x in form.fields["labels"].initial.split(",")}
        self.assertEqual(initial_labels, {"v1", "feature"})

        # POST updated labels
        update_form = TaskForm(
            data={
                "title": "Initial Task Updated",
                "priority": "MEDIUM",
                "status": "DONE",
                "labels": "v1, hotfix",
            },
            instance=task,
        )
        self.assertTrue(update_form.is_valid())
        updated_task = update_form.save()

        self.assertEqual(updated_task.status, Task.Status.DONE)
        self.assertEqual(
            set(updated_task.labels.values_list("name", flat=True)),
            {"v1", "hotfix"},
        )


class TaskViewAndPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            email="manager@example.com",
            username="manager",
            full_name="Manager User",
            password="password123",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member",
            full_name="Regular Member",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com",
            username="outsider",
            full_name="Outsider User",
            password="password123",
        )

        self.project = Project.objects.create(
            name="Secure Project",
            owner=self.owner,
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

        self.task = Task.objects.create(
            project=self.project,
            title="First Secure Task",
            description="Confidential task details",
            priority=Task.Priority.HIGH,
            status=Task.Status.TODO,
            created_by=self.owner,
            assignee=self.member,
        )
        label = TaskLabel.objects.create(project=self.project, name="security")
        self.task.labels.add(label)

    def test_anonymous_user_redirected_to_login(self):
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_outsider_cannot_access_project_tasks(self):
        self.client.login(email="outsider@example.com", password="password123")
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 404)

        detail_url = reverse(
            "tasks:task-detail",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)

    def test_member_and_manager_can_view_tasks_and_detail(self):
        self.client.login(email="member@example.com", password="password123")
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First Secure Task")
        self.assertContains(response, "security")

        detail_url = reverse(
            "tasks:task-detail",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confidential task details")
        self.assertContains(response, "security")

    def test_board_groups_tasks_by_defined_status_and_preserves_task_access(self):
        in_progress_task = Task.objects.create(
            project=self.project,
            title="In progress task",
            status=Task.Status.IN_PROGRESS,
            created_by=self.owner,
        )
        done_task = Task.objects.create(
            project=self.project,
            title="Completed task",
            status=Task.Status.DONE,
            created_by=self.owner,
        )
        self.client.force_login(self.member)
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})

        response = self.client.get(list_url, {"view": "board"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [column["status"] for column in response.context["task_columns"]],
            [status for status, _ in Task.Status.choices],
        )
        tasks_by_status = {
            column["status"]: column["tasks"]
            for column in response.context["task_columns"]
        }
        self.assertEqual(tasks_by_status[Task.Status.TODO], [self.task])
        self.assertEqual(tasks_by_status[Task.Status.IN_PROGRESS], [in_progress_task])
        self.assertEqual(tasks_by_status[Task.Status.DONE], [done_task])
        self.assertContains(response, "Tasks grouped by status")
        self.assertContains(response, "In progress task")
        self.assertContains(response, "Completed task")

    def test_task_list_remains_default_view(self):
        self.client.force_login(self.member)
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})

        response = self.client.get(list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["view_mode"], "list")
        self.assertEqual(response.context["task_columns"], [])
        self.assertContains(response, "First Secure Task")
        self.assertNotContains(response, "Tasks grouped by status")

    def test_authorized_manager_can_create_task(self):
        self.client.login(email="manager@example.com", password="password123")
        create_url = reverse("tasks:task-create", kwargs={"project_id": self.project.pk})

        response = self.client.post(
            create_url,
            data={
                "title": "New Manager Task",
                "description": "Detailed explanation",
                "priority": "CRITICAL",
                "due_date": "2026-11-15",
                "assignee": str(self.member.pk),
                "status": "TODO",
                "labels": "audit, core",
            },
        )
        self.assertEqual(response.status_code, 302)

        created_task = Task.objects.get(title="New Manager Task")
        self.assertEqual(created_task.priority, Task.Priority.CRITICAL)
        self.assertEqual(created_task.created_by, self.owner)
        self.assertEqual(created_task.assignee, self.member)
        self.assertEqual(
            set(created_task.labels.values_list("name", flat=True)),
            {"audit", "core"},
        )

    def test_non_manager_cannot_create_task(self):
        self.client.login(email="member@example.com", password="password123")
        create_url = reverse("tasks:task-create", kwargs={"project_id": self.project.pk})

        response = self.client.post(
            create_url,
            data={
                "title": "Unauthorized Task",
                "priority": "LOW",
                "status": "TODO",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_assignee_can_update_task_and_labels(self):
        self.client.login(email="member@example.com", password="password123")
        edit_url = reverse(
            "tasks:task-update",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )

        # Verify GET prepopulates existing values and labels in reusable task_form.html
        get_response = self.client.get(edit_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "value=\"First Secure Task\"")
        self.assertContains(get_response, "Confidential task details")
        self.assertContains(get_response, "value=\"security\"")

        # POST update
        post_response = self.client.post(
            edit_url,
            data={
                "title": "First Secure Task (In Progress)",
                "description": "Updated progress notes",
                "priority": "HIGH",
                "due_date": "",
                "assignee": str(self.member.pk),
                "status": "IN_PROGRESS",
                "labels": "security, in-review",
            },
        )
        self.assertEqual(post_response.status_code, 302)

        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "First Secure Task (In Progress)")
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(
            set(self.task.labels.values_list("name", flat=True)),
            {"security", "in-review"},
        )

    def test_invalid_submission_re_renders_form_and_preserves_values(self):
        self.client.login(email="manager@example.com", password="password123")
        create_url = reverse("tasks:task-create", kwargs={"project_id": self.project.pk})

        response = self.client.post(
            create_url,
            data={
                "title": "",  # missing required title
                "description": "Should be preserved",
                "priority": "HIGH",
                "due_date": "2026-11-20",
                "assignee": str(self.member.pk),
                "status": "TODO",
                "labels": "preserved-label",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertContains(response, "Should be preserved")
        self.assertContains(response, "value=\"preserved-label\"")
        self.assertContains(response, "value=\"2026-11-20\"")

    def test_real_csrf_protection_on_post_endpoints(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(email="manager@example.com", password="password123")
        create_url = reverse("tasks:task-create", kwargs={"project_id": self.project.pk})

        # POST without CSRF token should return 403 Forbidden
        response = csrf_client.post(
            create_url,
            data={"title": "No CSRF Task"},
        )
        self.assertEqual(response.status_code, 403)


class TaskCollaborationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_directory = tempfile.TemporaryDirectory()
        cls.media_settings = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.media_settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_settings.disable()
        cls.media_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.owner = User.objects.create_user(
            email="collab-owner@example.com",
            username="collab-owner",
            full_name="Project Owner",
        )
        self.member = User.objects.create_user(
            email="collab-member@example.com",
            username="collab-member",
            full_name="Task Assignee",
        )
        self.observer = User.objects.create_user(
            email="observer@example.com",
            username="observer",
            full_name="Project Observer",
        )
        self.outsider = User.objects.create_user(
            email="collab-outsider@example.com",
            username="collab-outsider",
            full_name="Outsider",
        )
        self.project = Project.objects.create(name="Collaboration", owner=self.owner)
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
        ProjectMembership.objects.create(
            project=self.project,
            user=self.observer,
            project_role=ProjectMembership.Role.TEAM_MEMBER,
        )
        self.task = Task.objects.create(
            project=self.project,
            title="Collaborative task",
            created_by=self.owner,
            assignee=self.member,
        )
        self.comment_url = reverse(
            "tasks:task-comment-create",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )
        self.upload_url = reverse(
            "tasks:task-attachment-upload",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )

    def test_comment_persists_author_and_creation_timestamp(self):
        self.client.force_login(self.member)

        response = self.client.post(self.comment_url, {"content": "Ready for review."})

        self.assertRedirects(
            response,
            reverse(
                "tasks:task-detail",
                kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
            ),
        )
        comment = TaskComment.objects.get()
        self.assertEqual(comment.task, self.task)
        self.assertEqual(comment.author, self.member)
        self.assertEqual(comment.content, "Ready for review.")
        self.assertIsNotNone(comment.created_at)
        self.assertLessEqual(timezone.now() - comment.created_at, timedelta(seconds=30))
        detail_response = self.client.get(
            reverse(
                "tasks:task-detail",
                kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
            )
        )
        self.assertContains(detail_response, "Ready for review.")
        self.assertContains(detail_response, "Task Assignee")

    def test_comments_render_in_chronological_order(self):
        earlier = TaskComment.objects.create(
            task=self.task,
            author=self.owner,
            content="First comment",
        )
        later = TaskComment.objects.create(
            task=self.task,
            author=self.member,
            content="Second comment",
        )
        TaskComment.objects.filter(pk=earlier.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        self.client.force_login(self.member)

        response = self.client.get(
            reverse(
                "tasks:task-detail",
                kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
            )
        )

        self.assertEqual(list(response.context["comments"]), [earlier, later])
        content = response.content.decode()
        self.assertLess(content.index("First comment"), content.index("Second comment"))

    def test_project_member_can_comment_without_task_edit_permission(self):
        self.assertTrue(self.project.memberships.filter(user=self.observer).exists())
        self.client.force_login(self.observer)

        response = self.client.post(
            self.comment_url,
            {"content": "I can collaborate without editing task fields."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TaskComment.objects.get().author, self.observer)

    def test_empty_comment_is_rejected_without_persisting(self):
        self.client.force_login(self.member)

        response = self.client.post(self.comment_url, {"content": "   "})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(TaskComment.objects.exists())

    def test_valid_attachment_upload_and_authorized_download(self):
        self.client.force_login(self.observer)
        uploaded_file = SimpleUploadedFile(
            "design.pdf",
            b"%PDF-1.4\nQA fixture\n%%EOF\n",
            content_type="application/pdf",
        )

        response = self.client.post(self.upload_url, {"file": uploaded_file})

        self.assertEqual(response.status_code, 302)
        attachment = TaskAttachment.objects.get()
        self.assertEqual(attachment.task, self.task)
        self.assertEqual(attachment.uploaded_by, self.observer)
        self.assertEqual(attachment.original_filename, "design.pdf")
        self.assertTrue(attachment.file.storage.exists(attachment.file.name))
        detail_response = self.client.get(
            reverse(
                "tasks:task-detail",
                kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
            )
        )
        self.assertContains(detail_response, "design.pdf")

        download_url = reverse(
            "tasks:task-attachment-download",
            kwargs={
                "project_id": self.project.pk,
                "task_id": self.task.pk,
                "attachment_id": attachment.pk,
            },
        )
        response = self.client.get(download_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn('attachment; filename="design.pdf"', response["Content-Disposition"])
        self.assertEqual(
            b"".join(response.streaming_content),
            b"%PDF-1.4\nQA fixture\n%%EOF\n",
        )

    def test_disallowed_file_type_is_rejected(self):
        self.client.force_login(self.member)

        response = self.client.post(
            self.upload_url,
            {
                "file": SimpleUploadedFile(
                    "payload.exe",
                    b"not allowed",
                    content_type="application/octet-stream",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unsupported file type")
        self.assertFalse(TaskAttachment.objects.exists())

    def test_allowed_extension_with_unrelated_content_is_rejected(self):
        self.client.force_login(self.member)

        response = self.client.post(
            self.upload_url,
            {
                "file": SimpleUploadedFile(
                    "renamed-executable.pdf",
                    b"MZThis is not a PDF file",
                    content_type="application/pdf",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "file contents do not match the .pdf file type")
        self.assertFalse(TaskAttachment.objects.exists())

    def test_empty_and_malformed_uploads_are_rejected(self):
        self.client.force_login(self.member)

        empty_response = self.client.post(
            self.upload_url,
            {"file": SimpleUploadedFile("empty.txt", b"", content_type="text/plain")},
        )
        self.assertEqual(empty_response.status_code, 200)
        self.assertContains(empty_response, "The uploaded file is empty.")
        self.assertFalse(TaskAttachment.objects.exists())

        malformed_response = self.client.post(
            self.upload_url,
            {
                "file": SimpleUploadedFile(
                    "broken.docx",
                    b"PK\x03\x04truncated office archive",
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        self.assertEqual(malformed_response.status_code, 200)
        self.assertContains(
            malformed_response,
            "file contents do not match the .docx file type",
        )
        self.assertFalse(TaskAttachment.objects.exists())

    def test_file_over_configured_size_is_rejected(self):
        self.client.force_login(self.member)
        with self.settings(TASK_ATTACHMENT_MAX_SIZE_BYTES=5):
            response = self.client.post(
                self.upload_url,
                {
                    "file": SimpleUploadedFile(
                        "notes.txt",
                        b"123456",
                        content_type="text/plain",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "File must be no larger than 5 bytes.")
        self.assertFalse(TaskAttachment.objects.exists())

    def test_invalid_upload_does_not_replace_existing_attachment(self):
        self.client.force_login(self.member)
        valid_file = SimpleUploadedFile("notes.txt", b"existing", content_type="text/plain")
        self.client.post(self.upload_url, {"file": valid_file})
        attachment = TaskAttachment.objects.get()

        response = self.client.post(
            self.upload_url,
            {"file": SimpleUploadedFile("payload.exe", b"invalid")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TaskAttachment.objects.count(), 1)
        self.assertTrue(attachment.file.storage.exists(attachment.file.name))

    def test_outsider_cannot_read_or_submit_comments_or_attachments(self):
        attachment = TaskAttachment.objects.create(
            task=self.task,
            uploaded_by=self.member,
            file=SimpleUploadedFile("private.txt", b"private"),
            original_filename="private.txt",
        )
        self.client.force_login(self.outsider)

        comment_response = self.client.get(
            reverse(
                "tasks:task-detail",
                kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
            )
        )
        add_comment_response = self.client.post(
            self.comment_url,
            {"content": "Unauthorized"},
        )
        upload_response = self.client.post(
            self.upload_url,
            {"file": SimpleUploadedFile("notes.txt", b"unauthorized")},
        )
        download_response = self.client.get(
            reverse(
                "tasks:task-attachment-download",
                kwargs={
                    "project_id": self.project.pk,
                    "task_id": self.task.pk,
                    "attachment_id": attachment.pk,
                },
            )
        )

        self.assertEqual(comment_response.status_code, 404)
        self.assertEqual(add_comment_response.status_code, 404)
        self.assertEqual(upload_response.status_code, 404)
        self.assertEqual(download_response.status_code, 404)
        self.assertFalse(TaskComment.objects.exists())
        self.assertEqual(TaskAttachment.objects.count(), 1)

    def test_comment_and_upload_posts_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.member)

        comment_response = csrf_client.post(
            self.comment_url,
            {"content": "Missing token"},
        )
        upload_response = csrf_client.post(
            self.upload_url,
            {"file": SimpleUploadedFile("notes.txt", b"missing token")},
        )

        self.assertEqual(comment_response.status_code, 403)
        self.assertEqual(upload_response.status_code, 403)
        self.assertFalse(TaskComment.objects.exists())
        self.assertFalse(TaskAttachment.objects.exists())
