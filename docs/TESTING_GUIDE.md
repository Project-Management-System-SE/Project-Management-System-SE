# Testing Guide

Reference for explaining the project's test coverage, test case count, source files, and CI execution.

## Test case count

The repository currently contains **272 test methods/functions** named `test_*` in **19 test modules**. This is **268 Django `TestCase`/`SimpleTestCase` methods** across 18 files in `backend/tests/`, plus **4 pytest-style functions** in `backend/pytest_tests/test_pms_smoke.py`. The Django tests are organized into 32 test classes. The count is the number of test methods/functions in the source code; parameterized `subTest` blocks and multiple assertions inside a test are not counted as separate tests.

Each of the five CI matrix jobs runs both suites: the 4 native pytest functions and the 268 Django test methods, for 272 test methods/functions per matrix job (1,360 executions total across all five variants), plus any `subTest` cases inside Django tests.

## Test modules and coverage

| Test file | Methods | Main coverage |
| --- | ---: | --- |
| `backend/tests/test_accounts.py` | 13 | Registration validation, duplicate emails, activation confirmation, password reset, expiry, and email failure handling. |
| `backend/tests/test_admin.py` | 1 | Custom user fields in the Django admin. |
| `backend/tests/test_api.py` | 12 | API authentication, project visibility, task filters and pagination, JSON validation, CSRF, permissions, CRUD, workflow checks, and audit behavior. |
| `backend/tests/test_audit.py` | 12 | Project/task audit events, deletion snapshots, authorization, ordering, immutability, and failed-operation behavior. |
| `backend/tests/test_backup_database.py` | 1 | Database backup contents, fixture manifest, and uploaded media. |
| `backend/tests/test_forms.py` | 10 | Project form validation, status choices, required fields, and date boundaries. |
| `backend/tests/test_foundation.py` | 14 | Installed apps, settings/security defaults, database configuration, health checks, and URL resolution. |
| `backend/tests/test_models.py` | 10 | User and project model behavior, password hashing, superuser rules, dates, and membership uniqueness. |
| `backend/tests/test_notifications.py` | 10 | Membership, task assignment/status, comment and due-date notifications, inbox privacy, and read permissions. |
| `backend/tests/test_project_analytics.py` | 2 | Sprint burndown calculations and completed-sprint velocity. |
| `backend/tests/test_project_management.py` | 24 | Project editing, visibility, membership roles, archive/delete permissions, CSRF, and confirmation. |
| `backend/tests/test_reports.py` | 5 | Progress, velocity and workload CSV reports, project scoping, and spreadsheet formula escaping. |
| `backend/tests/test_sprint_management.py` | 9 | Sprint/milestone constraints, planning permissions, carry-over, and displayed planning metrics. |
| `backend/tests/test_tasks.py` | 63 | Task models, labels, forms, task creation/edit/delete, permissions, filtering, pagination, comments, attachments, and CSRF. |
| `backend/tests/test_task_form_template.py` | 12 | Task form template rendering, field values, help and error messages, accessibility attributes, and multipart upload markup. |
| `backend/tests/test_task_status.py` | 20 | Workflow transitions, status forms, board updates, AJAX responses, CSRF, permissions, and invalid statuses. |
| `backend/tests/test_views.py` | 46 | Dashboard and project pages, project search and pagination, project creation, login/logout, permissions, and My Tasks. |
| `backend/tests/test_workflow_configuration.py` | 4 | Custom workflow configuration, transition validation, role access, and protection of states used by tasks. |
| `backend/pytest_tests/test_pms_smoke.py` | 4 | Pytest-style examples for password hashing, project visibility, member task-list access, and outsider denial. |
| **Total** | **272** | |

## What kinds of testing are present?

| Testing category | Project coverage | Explanation |
| --- | --- | --- |
| **Unit / domain tests** | Yes | Model, form, analytics, workflow, validation, and settings behavior is tested in isolation or with a small Django test database. Examples: `test_models.py`, `test_forms.py`, and `test_project_analytics.py`. |
| **Integration tests** | Yes; substantial | Django's test client exercises URL → view → form/model/database behavior, including sessions, permissions, CSRF, notifications, audit records, and API responses. Examples: `test_views.py`, `test_project_management.py`, `test_tasks.py`, and `test_api.py`. |
| **Template/component tests** | Partial | `test_task_form_template.py` directly checks template rendering, and many view tests assert that expected HTML/content is returned. There is no separate frontend component framework or isolated component test runner. |
| **System / end-to-end browser tests** | No dedicated automated suite | The repository does not include Selenium, Playwright, or another browser automation suite that drives a complete user journey in a real browser. Django client tests are not equivalent to deployed-browser end-to-end tests. |
| **API tests** | Yes | `test_api.py` tests the versioned JSON API with Django's client, including authentication, filtering, writes, CSRF, and authorization. |
| **Security/authorization tests** | Yes, within the Django suite | Tests cover outsider access, role restrictions, CSRF enforcement, secure settings, password flows, upload validation, and report scoping. There is no separate penetration test or security scanner configured in CI. |
| **Pytest** | Yes | `backend/requirements-dev.txt` installs pytest, pytest-django, and pytest-env. `pytest.ini` configures Django, isolated development-mode settings, and `backend/pytest_tests` as the discovery path. CI runs `python -m pytest -v` for the four native pytest functions, then runs the legacy Django test classes with Django's runner. |
| **Manual testing** | Not a recorded formal test plan in this repository | Browser checks and developer smoke checks may be performed during development, but no manual test execution log is included with the test suite. Record demo-day manual checks separately if the team performs them. |

### Explain the terminology accurately

The suite contains unit-style and integration-style tests, but these are not separate CI jobs. Most existing tests are Django test methods grouped by feature; the native pytest module uses plain test functions and pytest-django fixtures/markers. Most view tests use Django's test client, so they may cover several layers together (request handling, validation, database writes, and rendered responses). Do not describe all 272 as pure unit tests or as full end-to-end system tests. `pytest.ini` keeps the native pytest run focused on `backend/pytest_tests`; the existing Django classes run through Django's built-in runner.

## CI checks versus test cases

The workflow `.github/workflows/tests.yml` runs these checks in each matrix job:

1. Install dependencies from `backend/requirements-dev.txt` (which includes `backend/requirements.txt`, pytest, pytest-django, and pytest-env).
2. Run `python manage.py check`.
3. Run `python manage.py makemigrations --check --dry-run`.
4. Apply migrations with `python manage.py migrate --noinput`.
5. Run the four pytest-style tests with `python -m pytest -v` from the repository root.
6. Run the Django test suite with `python manage.py test tests -v 2` from `backend/`.

The first four steps are pipeline validation/setup; they are not additional test methods in the 268 count. The migration step uses the runner's development SQLite database and does not touch Render's production database.

## Running the suite locally

From the repository root:

```powershell
# Windows PowerShell
python -m pip install -r backend\requirements-dev.txt
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py migrate --noinput
python -m pytest -v
python backend\manage.py test tests -v 2
```

```sh
# Linux / macOS
python -m pip install -r backend/requirements-dev.txt
python backend/manage.py check
python backend/manage.py makemigrations --check --dry-run
python backend/manage.py migrate --noinput
python -m pytest -v
python backend/manage.py test tests -v 2
```

To run one module, for example:

```sh
python backend/manage.py test tests.test_project_analytics -v 2
```

## Recent development verification notes

- All four native pytest tests passed with `python -m pytest backend/pytest_tests/test_pms_smoke.py -v`.
- A full pytest collection of all test files was attempted during development: 262 passed, 10 failed, and 1 errored. It mixed legacy Django `TestCase` tests with pytest collection; failures included existing template/workflow expectations and Windows temporary-file cleanup. CI deliberately runs the native pytest smoke tests and legacy Django suite with their respective runners.
- A focused run of three task edit, comment, and status Django test methods passed their assertions. The command then reported a Windows `PermissionError` during `TaskCollaborationTests` temporary media-directory cleanup. This was a test-environment teardown error, so the command did not finish cleanly.
- Django system checks, migration checks, and `git diff --check` have also been run during development. These checks do not replace a successful full CI run.
- The Jira-inspired task table and the burndown chart rendering fix have not been verified by a dedicated browser automation test. The existing suite contains task-list/dashboard rendering coverage and burndown calculation coverage, respectively.

## Short answer for the demonstration

> “We have 272 automated tests across 19 files: 268 tests written as Django `TestCase` methods and four pytest-style functions. GitHub Actions runs the four pytest tests with pytest-django and the existing Django tests with Django's runner, across five Python/OS combinations. The suite covers domain logic, forms, integration behavior, templates, permissions, and the JSON API. We do not currently have a separate browser-based end-to-end suite.”

