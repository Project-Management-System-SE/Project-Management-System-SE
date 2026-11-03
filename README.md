# Project Management System (PMS)

A Software Engineering project designed to build a centralized, web-based platform for managing projects, tasks, workflows, sprints, and team collaboration.

---

## 👥 Team 11 Profile

| S.No. | Name | SRN | Role / Module Assignment |
| :---: | :--- | :--- | :--- |
| 1 | **Shivansh Sharma** | PES2UG24CS474 | Repo Setup, Architecture, CI/CD Pipeline |
| 2 | **Shibi R Shetty** | PES2UG24CS467 | Backend Architecture & Project Management Module |
| 3 | **Sheetal S Bevinakatti** | PES2UG24CS466 | Frontend Development , Testing & QA |
| 4 | **Shivanagouda I Patil** | PES2UG24CS471 | Requirements Analysis & Project Documentation |

---

## 🏗️ Architecture Overview

The system architecture follows a layered structure separating presentation, application business logic, and data persistence:

![PMS Architecture](docs/architecture.png)

- **Frontend**: HTML5, CSS, and JavaScript rendered via Django templates.
- **Backend API**: Python / Django framework structured into modular applications (`accounts`, `projects`, `tasks`).
- **Data Store**: Relational database (PostgreSQL in production / SQLite for local development & testing).
- **CI/CD Pipeline**: GitHub Actions for automated linting, migration verification, and test execution.

---

## 📁 Repository Structure

```text
Project-Management-System/
├── README.md               # Project overview, architecture, and team guide
├── .gitignore              # Git ignore rules for Python, Django, and virtual environments
├── backend/                # Django backend application root
│   ├── manage.py           # Django administrative utility
│   ├── requirements.txt    # Python dependencies list
│   ├── config/             # Django settings and main URL configuration
│   ├── accounts/           # User authentication and profile module
│   ├── projects/           # Project management module
│   ├── tasks/              # Task and Kanban management module
│   └── tests/              # Test suite for unit and integration testing
├── docs/                   # Approved documents, specifications, and architecture
│   ├── SRS.pdf             # Software Requirements Specification
│   ├── Software-Test-Plan.pdf # Software Test Plan (STP)
│   ├── architecture.png    # System architecture and data flow diagram
│   ├── Project_Proposal.pdf
│   ├── SASD_Specification.docx
│   ├── Sprint1_Requirements_Analysis.pdf
│   └── Requirements_Matrix.pdf
├── templates/              # Django HTML templates (Frontend)
├── static/                 # Static assets: CSS, JavaScript, and images
└── .github/
    └── workflows/
        └── tests.yml       # GitHub Actions automated test workflow
```

---

## 🚀 Getting Started

### 1. Clone Repository
```bash
git clone https://github.com/Project-Management-System-SE/Project-Management-System-SE.git
cd Project-Management-System-SE
```

### 2. Setup Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### 4. Configure email for password resets

For local development, use Django's console email backend so registration confirmation emails and
password-reset links are printed in the development server output instead of requiring an SMTP
account.

After login, the session remains active for 30 days without requiring an extra checkbox. The
browser can offer to save and autofill the email and password using its password manager; the
application does not store a readable copy of the password.

```powershell
# Windows PowerShell
$env:DJANGO_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
```

```bash
# Linux / macOS
export DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

For deployment, configure an SMTP backend and provide the mail server settings through
environment variables: `DJANGO_EMAIL_BACKEND`, `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`,
`DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_EMAIL_USE_TLS`, and
`DJANGO_DEFAULT_FROM_EMAIL`. Do not commit credentials. Password-reset links expire after 24 hours.

### 5. Run the application

The development entry point enables Django debug mode by default, so `runserver`
serves the files in the repository's `static/` directory:

```powershell
# Windows PowerShell
python manage.py runserver
```

```bash
# Linux / macOS
python manage.py runserver
```

```bash
python backend/manage.py migrate
python backend/manage.py runserver
```

If you invoke Django through another entry point, enable development static-file
serving explicitly:

```powershell
# Windows PowerShell
$env:DJANGO_DEBUG = "true"
```

```bash
# Linux / macOS
export DJANGO_DEBUG=true
```

To explicitly disable debug mode, set `DJANGO_DEBUG=false` and provide a
`DJANGO_SECRET_KEY`.

### Project management

Open **Projects** and select **View project** to see project details and membership. Project
Admins and that project's Project Managers can edit, archive, and delete it. Project Managers may
add or remove active, non-admin users as Team Members; only Admins can grant or remove a
Project Manager role. A project's owner remains a Project Manager and cannot be removed from its
own membership. Deletion requires confirmation and removes the project and its memberships, not
the member accounts. Project changes and membership mutations require authenticated, CSRF-protected
requests.

Open a project's **Tasks** page to switch between the task list and a status board. Task cards link
to their details; users with task edit permission can update status and other task fields there.
The dashboard counts tasks assigned to the signed-in user within visible projects, and project
progress is the percentage of tasks marked Done. Use **My Tasks** to view those assigned tasks.
Project and task search supports the currently available fields; sprint and milestone planning is
available from each project's planning page.

Task attachments are stored below `backend/media` by default (override with `DJANGO_MEDIA_ROOT`)
and are served only through authenticated, project-authorized downloads. Configure the upload limit
with `TASK_ATTACHMENT_MAX_SIZE_BYTES` (default 10 MiB) and the comma-separated extension allowlist
with `TASK_ATTACHMENT_ALLOWED_EXTENSIONS` (default: `pdf,txt,csv,png,jpg,jpeg,gif,doc,docx,xls,xlsx`).
Uploads must be non-empty, within the size limit, and pass a standard-library signature or structure
check for the selected extension. This content validation is not malware scanning.

**Issue #19 permission coordination:** collaboration currently follows `can_view_tasks_for`: active
project members, project owners, and admins may view and add comments or attachments, while task
editing continues to use the narrower `can_edit_task` rule. Confirm this distinction with the
issue #19 owner before changing collaboration permissions.

### Task viewing and status updates

Open **Tasks** in the sidebar or choose **View tasks** from a project. Project members can view
tasks in projects they can access. Project Admins and Project Managers can update any task
status; an authorized project member can update a task assigned to them or created by them.
Supported statuses are **To Do**, **In Progress**, and **Done**. Task details also support
creation, editing, and project-scoped labels.

Invalid status values are rejected without changing the saved task. Run
`python backend/manage.py migrate` after pulling changes to apply database migrations.

### Task and membership notifications

The application stores notifications in the signed-in user's **Notifications** inbox when they are
added to or removed from a project, assigned a task, or notified about a task status change or
comment. Status and comment notifications go to the task assignee and creator, excluding the
person who made the change. Task assignees receive one in-app due-date reminder the day before a
task is due. Registration confirmation and password-reset messages continue to use email.

Run `python backend/manage.py send_due_date_reminders` daily to create due-date reminders. Schedule
this command with Windows Task Scheduler or a deployment scheduler; the command records sent
reminders so repeated runs do not create duplicates.
