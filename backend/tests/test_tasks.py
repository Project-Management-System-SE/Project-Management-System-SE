import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import RestrictedError
from django.template.loader import render_to_string
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

    def test_valid_task_persistence(self):
        task = Task.objects.create(
            project=self.project,
            title="  Persisted task  ",
            description="Task details",
            priority=Task.Priority.HIGH,
            status=Task.Status.IN_PROGRESS,
            assignee=self.member,
            created_by=self.owner,
        )

        task.refresh_from_db()
        self.assertEqual(task.title, "Persisted task")
        self.assertEqual(task.description, "Task details")
        self.assertEqual(task.project, self.project)
        self.assertEqual(task.assignee, self.member)
        self.assertEqual(task.created_by, self.owner)

    def test_effort_values_persist_and_actual_may_exceed_estimate(self):
        task = Task.objects.create(
            project=self.project,
            title="Effort tracking",
            estimated_effort=Decimal("1.25"),
            actual_effort=Decimal("2.50"),
            created_by=self.owner,
        )

        task.refresh_from_db()
        self.assertEqual(task.estimated_effort, Decimal("1.25"))
        self.assertEqual(task.actual_effort, Decimal("2.50"))

    def test_zero_and_blank_effort_values_are_allowed(self):
        zero_task = Task.objects.create(
            project=self.project,
            title="Zero effort",
            estimated_effort=Decimal("0.00"),
            actual_effort=Decimal("0.00"),
            created_by=self.owner,
        )
        blank_task = Task.objects.create(
            project=self.project,
            title="Blank effort",
            created_by=self.owner,
        )

        zero_task.refresh_from_db()
        blank_task.refresh_from_db()
        self.assertEqual(zero_task.estimated_effort, Decimal("0.00"))
        self.assertEqual(zero_task.actual_effort, Decimal("0.00"))
        self.assertIsNone(blank_task.estimated_effort)
        self.assertIsNone(blank_task.actual_effort)

    def test_negative_effort_values_are_rejected_by_database_constraints(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Task.objects.bulk_create(
                    [
                        Task(
                            project=self.project,
                            title="Negative estimate",
                            estimated_effort=Decimal("-0.01"),
                            created_by=self.owner,
                        )
                    ]
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Task.objects.bulk_create(
                    [
                        Task(
                            project=self.project,
                            title="Negative actual",
                            actual_effort=Decimal("-0.01"),
                            created_by=self.owner,
                        )
                    ]
                )

    def test_task_assignee_validation_must_be_project_member(self):
        task = Task(
            project=self.project,
            title="Invalid assignee task",
            created_by=self.owner,
            assignee=self.other_user,
        )
        with self.assertRaises(ValidationError):
            task.clean()

    def test_invalid_assignee_is_rejected_when_saved(self):
        task = Task(
            project=self.project,
            title="Invalid assignee task",
            created_by=self.owner,
            assignee=self.other_user,
        )

        with self.assertRaises(ValidationError):
            task.save()

    def test_invalid_status_and_priority_are_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Task.objects.bulk_create(
                    [
                        Task(
                            project=self.project,
                            title="Invalid status",
                            status="INVALID",
                            created_by=self.owner,
                        )
                    ]
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Task.objects.bulk_create(
                    [
                        Task(
                            project=self.project,
                            title="Invalid priority",
                            priority="INVALID",
                            created_by=self.owner,
                        )
                    ]
                )

    def test_task_indexes_cover_project_status_and_project_created_order(self):
        constraints = connection.introspection.get_constraints(
            connection.cursor(), Task._meta.db_table
        )
        index_columns = {
            tuple(details["columns"])
            for details in constraints.values()
            if details.get("index")
        }

        self.assertIn(("project_id", "status"), index_columns)
        self.assertIn(("project_id", "created_at"), index_columns)

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

        task = Task.objects.create(
            project=self.project,
            title="Project-scoped labels",
            created_by=self.owner,
        )
        with self.assertRaises(ValidationError):
            task.labels.add(label_b)

    def test_reverse_label_assignment_rejects_cross_project_task(self):
        project_b = Project.objects.create(name="Beta Project", owner=self.owner)
        label = TaskLabel.objects.create(project=self.project, name="urgent")
        task = Task.objects.create(
            project=project_b,
            title="Other project task",
            created_by=self.owner,
        )

        with self.assertRaises(ValidationError):
            label.tasks.add(task)

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

    def test_creator_cannot_be_deleted_while_referenced(self):
        creator = User.objects.create_user(
            email="creator@example.com",
            username="creator",
            full_name="Task Creator",
            password="safe-password-123",
        )
        task = Task.objects.create(
            project=self.project,
            title="Protected creator",
            created_by=creator,
        )

        with self.assertRaises(RestrictedError):
            creator.delete()

        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def test_deleted_assignee_is_set_to_null(self):
        task = Task.objects.create(
            project=self.project,
            title="Nullable assignee",
            assignee=self.member,
            created_by=self.owner,
        )

        self.member.delete()

        task.refresh_from_db()
        self.assertIsNone(task.assignee_id)

    def test_completed_timestamp_is_set_and_cleared_with_status(self):
        task = Task.objects.create(
            project=self.project,
            title="Completion lifecycle",
            created_by=self.owner,
        )
        self.assertIsNone(task.completed_at)

        task.status = Task.Status.DONE
        task.save(update_fields={"status"})
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)

        task.status = Task.Status.IN_PROGRESS
        task.save(update_fields={"status"})
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)


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
                "estimated_effort": "4.25",
                "actual_effort": "3.50",
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
        self.assertEqual(task.estimated_effort, Decimal("4.25"))
        self.assertEqual(task.actual_effort, Decimal("3.50"))
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

    def test_assignee_queryset_contains_members_owner_excludes_outsiders_and_allows_unassigned(
        self,
    ):
        form = TaskForm(project=self.project)
        assignee_queryset = form.fields["assignee"].queryset

        self.assertEqual(
            set(assignee_queryset.values_list("pk", flat=True)),
            {self.owner.pk, self.member.pk},
        )
        self.assertEqual(form.fields["assignee"].empty_label, "Unassigned")

    def test_edit_form_prepopulates_all_task_values(self):
        label = TaskLabel.objects.create(project=self.project, name="frontend")
        task = Task.objects.create(
            project=self.project,
            title="Existing task",
            description="Existing description",
            priority=Task.Priority.HIGH,
            due_date=date(2026, 12, 31),
            assignee=self.member,
            status=Task.Status.IN_PROGRESS,
            created_by=self.owner,
        )
        task.labels.add(label)

        form = TaskForm(instance=task)

        self.assertEqual(form.initial["title"], "Existing task")
        self.assertEqual(form.initial["description"], "Existing description")
        self.assertEqual(form.initial["priority"], Task.Priority.HIGH)
        self.assertEqual(form.initial["due_date"], date(2026, 12, 31))
        self.assertEqual(form.initial["assignee"], self.member.pk)
        self.assertEqual(form.initial["status"], Task.Status.IN_PROGRESS)
        self.assertEqual(form.fields["labels"].initial, "frontend")

    def test_actual_task_form_rejects_invalid_priority(self):
        form = TaskForm(
            data={
                "title": "Invalid priority task",
                "priority": "NOT_A_PRIORITY",
                "status": Task.Status.TODO,
            },
            project=self.project,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("priority", form.errors)

    def test_task_form_validates_effort_values_and_precision(self):
        valid_form = TaskForm(
            data={
                "title": "Effort form task",
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.TODO,
                "estimated_effort": "2.50",
                "actual_effort": "3.75",
            },
            project=self.project,
        )
        negative_form = TaskForm(
            data={
                "title": "Negative effort task",
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.TODO,
                "estimated_effort": "-0.01",
            },
            project=self.project,
        )
        precision_form = TaskForm(
            data={
                "title": "Precise effort task",
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.TODO,
                "estimated_effort": "1.234",
            },
            project=self.project,
        )

        self.assertTrue(valid_form.is_valid(), valid_form.errors)
        self.assertEqual(
            valid_form.cleaned_data["estimated_effort"], Decimal("2.50")
        )
        self.assertEqual(valid_form.cleaned_data["actual_effort"], Decimal("3.75"))
        self.assertFalse(negative_form.is_valid())
        self.assertIn("estimated_effort", negative_form.errors)
        self.assertFalse(precision_form.is_valid())
        self.assertIn("estimated_effort", precision_form.errors)

    def test_actual_task_form_renders_field_and_non_field_errors(self):
        form = TaskForm(
            data={
                "title": "Invalid priority task",
                "priority": "NOT_A_PRIORITY",
                "status": Task.Status.TODO,
            },
            project=self.project,
        )
        self.assertFalse(form.is_valid())
        form.add_error(None, "Task could not be saved.")

        html = render_to_string(
            "task_form.html",
            {
                "form": form,
                "form_heading": "Create task",
                "submit_label": "Create task",
            },
        )

        self.assertIn('id="id_priority_errors"', html)
        self.assertIn('class="field-errors"', html)
        self.assertIn('role="alert"', html)
        self.assertIn("Select a valid choice", html)
        self.assertIn("Task could not be saved.", html)
        self.assertIn('class="form-errors"', html)

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
                "estimated_effort": "8.00",
                "actual_effort": "10.25",
                "labels": "v1, hotfix",
            },
            instance=task,
        )
        self.assertTrue(update_form.is_valid())
        updated_task = update_form.save()

        self.assertEqual(updated_task.status, Task.Status.DONE)
        self.assertEqual(updated_task.estimated_effort, Decimal("8.00"))
        self.assertEqual(updated_task.actual_effort, Decimal("10.25"))
        self.assertEqual(
            set(updated_task.labels.values_list("name", flat=True)),
            {"v1", "hotfix"},
        )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
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

    def test_task_filters_combine_keyword_assignee_priority_status_and_label(self):
        matching_label = self.task.labels.get()
        other_task = Task.objects.create(
            project=self.project,
            title="First Secure Task follow-up",
            description="Confidential task details",
            priority=Task.Priority.LOW,
            status=Task.Status.DONE,
            created_by=self.owner,
            assignee=self.owner,
        )
        other_label = TaskLabel.objects.create(
            project=self.project,
            name="follow-up",
        )
        other_task.labels.add(other_label)
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})
        self.client.force_login(self.member)

        response = self.client.get(
            list_url,
            {
                "q": "First Secure",
                "assignee": str(self.member.pk),
                "priority": Task.Priority.HIGH,
                "status": Task.Status.TODO,
                "label": str(matching_label.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["tasks"].values_list("pk", flat=True)),
            [self.task.pk],
        )
        self.assertContains(response, "First Secure Task")
        self.assertNotContains(response, "First Secure Task follow-up")

    def test_task_filter_empty_state_and_clear_link(self):
        self.client.force_login(self.member)
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})

        response = self.client.get(list_url, {"q": "no matching task", "view": "board"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["view_mode"], "board")
        self.assertEqual(list(response.context["tasks"]), [])
        self.assertContains(response, "No tasks in this status.")
        self.assertContains(response, "Clear filters")

    def test_invalid_assignee_filter_is_rejected(self):
        self.client.force_login(self.member)
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})

        response = self.client.get(list_url, {"assignee": str(self.outsider.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["filter_form"].is_valid())
        self.assertEqual(list(response.context["tasks"]), [])
        self.assertContains(response, "Select a valid choice")

    def test_task_list_paginates_filtered_results_and_preserves_search(self):
        for index in range(21):
            Task.objects.create(
                project=self.project,
                title=f"Paged task {index}",
                created_by=self.owner,
            )
        self.client.force_login(self.member)
        list_url = reverse("tasks:task-list", kwargs={"project_id": self.project.pk})

        first_page = self.client.get(list_url, {"q": "Paged"})
        second_page = self.client.get(list_url, {"q": "Paged", "page": "2"})

        self.assertEqual(first_page.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(first_page.context["tasks"]), 20)
        self.assertContains(first_page, "q=Paged&amp;page=2")
        self.assertEqual(len(second_page.context["tasks"]), 1)

    def test_task_detail_and_list_display_effort_values(self):
        self.task.estimated_effort = Decimal("4.25")
        self.task.actual_effort = Decimal("5.50")
        self.task.save()
        self.client.force_login(self.member)

        detail_response = self.client.get(
            reverse(
                "tasks:task-detail",
                kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
            )
        )
        list_response = self.client.get(
            reverse("tasks:task-list", kwargs={"project_id": self.project.pk})
        )

        self.assertContains(detail_response, "4.25 hours")
        self.assertContains(detail_response, "5.50 hours")
        self.assertContains(list_response, "4.25h")
        self.assertContains(list_response, "5.50h")

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
                "estimated_effort": "6.00",
                "actual_effort": "7.25",
                "assignee": str(self.member.pk),
                "status": "TODO",
                "labels": "audit, core",
            },
        )
        self.assertEqual(response.status_code, 302)

        created_task = Task.objects.get(title="New Manager Task")
        self.assertEqual(created_task.priority, Task.Priority.CRITICAL)
        self.assertEqual(created_task.estimated_effort, Decimal("6.00"))
        self.assertEqual(created_task.actual_effort, Decimal("7.25"))
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

    def test_create_rejects_outsider_assignee_without_persisting_task(self):
        self.client.force_login(self.owner)
        create_url = reverse("tasks:task-create", kwargs={"project_id": self.project.pk})

        response = self.client.post(
            create_url,
            data={
                "title": "Task with outsider",
                "description": "Should not be saved",
                "priority": "HIGH",
                "status": "TODO",
                "assignee": str(self.outsider.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("assignee", response.context["form"].errors)
        self.assertFalse(Task.objects.filter(title="Task with outsider").exists())

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
                "estimated_effort": "8.00",
                "actual_effort": "9.50",
                "assignee": str(self.member.pk),
                "status": "IN_PROGRESS",
                "labels": "security, in-review",
            },
        )
        self.assertEqual(post_response.status_code, 302)

        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "First Secure Task (In Progress)")
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(self.task.estimated_effort, Decimal("8.00"))
        self.assertEqual(self.task.actual_effort, Decimal("9.50"))
        self.assertEqual(
            set(self.task.labels.values_list("name", flat=True)),
            {"security", "in-review"},
        )

    def test_edit_rejects_outsider_assignee_without_changing_task(self):
        self.client.force_login(self.member)
        edit_url = reverse(
            "tasks:task-update",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )

        response = self.client.post(
            edit_url,
            data={
                "title": "Attempted unauthorized assignment",
                "description": "Should not be saved",
                "priority": "LOW",
                "status": "IN_PROGRESS",
                "assignee": str(self.outsider.pk),
                "labels": "security",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("assignee", response.context["form"].errors)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "First Secure Task")
        self.assertEqual(self.task.description, "Confidential task details")
        self.assertEqual(self.task.priority, Task.Priority.HIGH)
        self.assertEqual(self.task.status, Task.Status.TODO)
        self.assertEqual(self.task.assignee, self.member)

    def test_outsider_cannot_edit_task(self):
        self.client.force_login(self.outsider)
        edit_url = reverse(
            "tasks:task-update",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )

        response = self.client.post(
            edit_url,
            data={
                "title": "Unauthorized edit",
                "priority": "LOW",
                "status": "TODO",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "First Secure Task")
        self.assertEqual(self.task.assignee, self.member)

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

    def test_real_csrf_protection_on_task_edit_endpoint(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.member)
        edit_url = reverse(
            "tasks:task-update",
            kwargs={"project_id": self.project.pk, "task_id": self.task.pk},
        )

        response = csrf_client.post(
            edit_url,
            data={
                "title": "CSRF bypass attempt",
                "priority": "LOW",
                "status": "TODO",
                "assignee": str(self.member.pk),
            },
        )

        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "First Secure Task")
        self.assertEqual(self.task.priority, Task.Priority.HIGH)
        self.assertEqual(self.task.assignee, self.member)


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
