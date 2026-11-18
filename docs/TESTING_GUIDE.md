# Testing Guide

Reference for explaining the project's test coverage, test case count, source files, and CI execution.

## Test case count

The current source inventory contains **358 test methods/functions** named `test_*` in **34 test modules**: **354 Django `TestCase`/`SimpleTestCase` methods** across 33 files in `backend/tests/`, plus **4 native pytest functions** in `backend/pytest_tests/test_pms_smoke.py`. The Django tests are organized into 48 test classes. This is a static count of test definitions; `subTest` cases and multiple assertions are not counted separately. It does not mean all tests passed in the latest CI run.

Each of the five CI matrix jobs is configured to run both suites: 4 native pytest functions and 354 Django test methods, for 358 test methods/functions per matrix job (1,790 executions across all five variants), plus any `subTest` cases inside Django tests. Check GitHub Actions for actual pass/fail results.

## Test modules and coverage

| Test file | Methods | Main coverage |
| --- | ---: | --- |
| `backend/tests/test_accounts.py` | 13 | Registration validation, duplicate emails, activation confirmation, password reset, expiry, and email failure handling. |
| `backend/tests/test_admin.py` | 1 | Custom user fields in the Django admin. |
| `backend/tests/test_api.py` | 13 | API authentication, project visibility, task filters and pagination, JSON validation, CSRF, permissions, CRUD, workflow checks, and audit behavior. |
| `backend/tests/test_api_comments_reports.py` | 4 | Comment API CRUD, payload validation, cross-project access, and structured reports. |
| `backend/tests/test_api_integration_docs.py` | 6 | OpenAPI schema, API documentation viewer, and integration guide coverage. |
| `backend/tests/test_api_memberships.py` | 4 | Membership API list/add/update/remove and owner-only permissions. |
| `backend/tests/test_api_pagination.py` | 4 | API pagination boundaries, combined filters, query validation, and project-list filtering. |
| `backend/tests/test_api_security_permissions.py` | 5 | Cross-project access, role restrictions, task status permissions, and workflow protections. |
| `backend/tests/test_api_throttling.py` | 3 | Per-user read limits, write throttling, and session API rate limits. |
| `backend/tests/test_api_workflow_sprints.py` | 4 | Workflow settings, sprint/milestone CRUD, and manager permissions. |
| `backend/tests/test_audit.py` | 12 | Project/task audit events, deletion snapshots, authorization, ordering, immutability, and failed-operation behavior. |
| `backend/tests/test_backup_database.py` | 1 | Database backup contents, fixture manifest, and uploaded media. |
| `backend/tests/test_database_config.py` | 1 | Database connection configuration command. |
| `backend/tests/test_forms.py` | 10 | Project form validation, status choices, required fields, and date boundaries. |
| `backend/tests/test_foundation.py` | 16 | Installed apps, settings/security defaults, database configuration, health checks, and URL resolution. |
| `backend/tests/test_models.py` | 10 | User and project model behavior, password hashing, superuser rules, dates, and membership uniqueness. |
| `backend/tests/test_notifications.py` | 10 | Membership, task assignment/status, comment and due-date notifications, inbox privacy, and read permissions. |
| `backend/tests/test_production_security.py` | 3 | Password hasher, security headers, and production-security management command. |
| `backend/tests/test_project_analytics.py` | 2 | Sprint burndown calculations and completed-sprint velocity. |
| `backend/tests/test_project_management.py` | 24 | Project editing, visibility, membership roles, archive/delete permissions, CSRF, and confirmation. |
| `backend/tests/test_reports.py` | 5 | Progress, velocity and workload CSV reports, project scoping, and spreadsheet formula escaping. |
| `backend/tests/test_reports_metrics.py` | 11 | Project/sprint metrics, velocity, burndown calculations, edge cases, and CSV generation. |
| `backend/tests/test_reports_security.py` | 5 | Login requirements, project visibility, and report download authorization. |
| `backend/tests/test_rest_api.py` | 10 | API authentication, task writes/status, CSRF, OpenAPI/docs, and consistent error responses. |
| `backend/tests/test_sprint_management.py` | 9 | Sprint/milestone constraints, planning permissions, carry-over, and displayed planning metrics. |
| `backend/tests/test_tasks.py` | 63 | Task models, labels, forms, task creation/edit/delete, permissions, filtering, pagination, comments, attachments, and CSRF. |
| `backend/tests/test_task_form_template.py` | 12 | Task form template rendering, field values, help and error messages, accessibility attributes, and multipart upload markup. |
| `backend/tests/test_task_permissions.py` | 5 | Task view, create, edit, reassign, and delete permission rules. |
| `backend/tests/test_task_status.py` | 20 | Workflow transitions, status forms, board updates, AJAX responses, CSRF, permissions, and invalid statuses. |
| `backend/tests/test_task_validation.py` | 5 | Task title validation, XSS rejection, due dates, and project-member assignee validation. |
| `backend/tests/test_views.py` | 49 | Dashboard and project pages, project search and pagination, project creation, login/logout, permissions, and My Tasks. |
| `backend/tests/test_workflow_configuration.py` | 8 | Custom workflow configuration, transition validation, role access, and protection of states used by tasks. |
| `backend/tests/test_workflow_transitions.py` | 6 | Default and custom task workflow transition rules and validation errors. |
| `backend/pytest_tests/test_pms_smoke.py` | 4 | Pytest-style examples for password hashing, project visibility, member task-list access, and outsider denial. |
| **Total** | **358** | **354 Django test methods plus 4 pytest-style functions.** |

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

The suite contains unit-style and integration-style tests, but these are not separate CI jobs. Most existing tests are Django test methods grouped by feature; the native pytest module uses plain test functions and pytest-django fixtures/markers. Most view tests use Django's test client, so they may cover several layers together (request handling, validation, database writes, and rendered responses). Do not describe all 358 as pure unit tests or as full end-to-end system tests. `pytest.ini` keeps the native pytest run focused on `backend/pytest_tests`; the existing Django classes run through Django's built-in runner.

## CI checks versus test cases

The workflow `.github/workflows/tests.yml` runs these checks in each of five matrix jobs: Ubuntu with Python 3.11, 3.12, and 3.13; Windows with Python 3.13; and macOS with Python 3.13.

1. Install dependencies from `backend/requirements-dev.txt` (which includes `backend/requirements.txt`, pytest, pytest-django, and pytest-env).
2. Run `python manage.py check`.
3. Run `python manage.py makemigrations --check --dry-run`.
4. Apply migrations with `python manage.py migrate --noinput`.
5. Run the four pytest-style tests with `python -m pytest -v` from the repository root. `pytest.ini` points pytest discovery at `backend/pytest_tests`, so this command does not collect the Django suite.
6. Run the Django test suite with `python manage.py test tests -v 2` from `backend/`.

The first four steps are pipeline validation/setup; they are not additional test methods in the 354 count. The migration step uses the runner's development SQLite database and does not touch Render's production database.

Render deployment is separate from test execution. `.github/workflows/deploy-render.yml` triggers after successful CI for a push to `main` and requires the `RENDER_DEPLOY_HOOK_URL` secret in GitHub's `production` environment. A missing secret fails that deploy job; it does not mean the pytest suite failed. Render Auto-Deploy is a separate deployment path.

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

- A recorded focused run passed all four native pytest tests with `python -m pytest backend/pytest_tests/test_pms_smoke.py -v`. This is a prior result; check the latest GitHub Actions run for the current pass/fail status.
- On an earlier repository snapshot, a full pytest collection of all then-existing test files was attempted: 262 passed, 10 failed, and 1 errored. It mixed legacy Django `TestCase` tests with pytest collection; failures included template/workflow expectations and Windows temporary-file cleanup. These historical numbers do not describe the current 358-test source inventory. CI deliberately runs the native pytest smoke tests and Django suite with their respective runners.
- A focused run of three task edit, comment, and status Django test methods passed their assertions. The command then reported a Windows `PermissionError` during `TaskCollaborationTests` temporary media-directory cleanup. This was a test-environment teardown error, so the command did not finish cleanly.
- Django system checks, migration checks, and `git diff --check` have also been run during development. These checks do not replace a successful full CI run.
- The Jira-inspired task table and the burndown chart rendering fix have not been verified by a dedicated browser automation test. The existing suite contains task-list/dashboard rendering coverage and burndown calculation coverage, respectively.

## Short answer for the demonstration

> “We have 358 test methods/functions in 34 test modules: 354 Django test methods and four native pytest smoke tests. GitHub Actions is configured to run the pytest suite with pytest-django and the Django suite with Django's runner across five Python/OS combinations. The suite covers domain logic, forms, request/database integration, templates, permissions, and the JSON API. We do not currently have a separate browser-based end-to-end suite. This is the source count; I check Actions for the actual run result.”

