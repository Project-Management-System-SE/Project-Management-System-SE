# API Integration Examples

This document provides practical examples for integrating with the Project Management System REST API. For the full OpenAPI 3.0 specification visit `/api/v1/docs/` or download `/api/v1/openapi.json`.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Error Response Format](#error-response-format)
3. [Rate Limiting](#rate-limiting)
4. [Pagination and Filtering](#pagination-and-filtering)
5. [Projects](#projects)
6. [Tasks](#tasks)
7. [Task Status and Workflow](#task-status-and-workflow)
8. [Project Memberships](#project-memberships)
9. [Workflow Configuration](#workflow-configuration)
10. [Sprints](#sprints)
11. [Milestones](#milestones)
12. [Task Comments](#task-comments)
13. [Project Reports](#project-reports)

---

## Authentication

All endpoints require authentication. Two mechanisms are supported.

### Bearer Token (recommended for integrations)

Obtain an API token from your account settings page. Pass it in every request:

```http
GET /api/v1/projects/ HTTP/1.1
Host: your-instance.example.com
Authorization: Bearer pm_abc123yourtoken
```

**curl:**
```bash
curl -H "Authorization: Bearer pm_abc123yourtoken" \
     https://your-instance.example.com/api/v1/projects/
```

**Python (requests):**
```python
import requests

HEADERS = {"Authorization": "Bearer pm_abc123yourtoken"}
BASE = "https://your-instance.example.com/api/v1"

resp = requests.get(f"{BASE}/projects/", headers=HEADERS)
resp.raise_for_status()
projects = resp.json()["data"]["projects"]
```

### Session Cookie (browser / web UI)

After logging in through the web UI the browser holds a `sessionid` cookie. Session authentication is accepted for all GET requests and for the legacy `/api/v1/session/` endpoints.

> **Note** – Unsafe methods (POST / PATCH / PUT / DELETE) on `/api/v1/` endpoints require a Bearer token; session authentication alone is not accepted for writes on the JSON API to prevent CSRF attacks.

---

## Error Response Format

All error responses share a consistent envelope regardless of status code:

```json
{
  "status": "error",
  "message": "A human-readable description of what went wrong.",
  "errors": {
    "field_name": ["Validation message for this field."],
    "__all__": ["Non-field error message."]
  }
}
```

| HTTP status | Meaning |
|-------------|---------|
| `400` | Validation error or bad request |
| `401` | Missing or invalid authentication |
| `403` | Authenticated but not permitted |
| `404` | Resource not found or hidden from caller |
| `405` | HTTP method not allowed on this endpoint |
| `415` | `Content-Type` must be `application/json` |
| `429` | Rate limit exceeded (see `Retry-After` header) |

**Example – validation error:**
```json
{
  "status": "error",
  "message": "Task validation failed.",
  "errors": {
    "title": ["Ensure this field has at least 3 characters."],
    "due_date": ["Enter a valid date."]
  }
}
```

**Example – 404:**
```json
{
  "status": "error",
  "message": "Project not found or access denied.",
  "errors": {}
}
```

---

## Rate Limiting

The API enforces per-user rate limits (per IP for anonymous callers):

| Request type | Default limit |
|---|---|
| Read (GET / HEAD) | 60 requests per 60 seconds |
| Write (POST / PATCH / PUT / DELETE) | 20 requests per 60 seconds |

When the limit is exceeded the API returns `429 Too Many Requests`:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{
  "status": "error",
  "message": "API rate limit exceeded. Try again later.",
  "errors": {"rate_limit": ["Request limit exceeded."]}
}
```

**Handling 429 in Python:**
```python
import time
import requests

def api_get(url, headers):
    for attempt in range(3):
        resp = requests.get(url, headers=headers)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("Rate limit retries exhausted.")
```

---

## Pagination and Filtering

All list endpoints return paginated results. The response envelope always includes:

```json
{
  "status": "success",
  "data": {
    "<resource_key>": [...],
    "count": 42,
    "page": 2,
    "page_size": 10,
    "next_page": 3,
    "previous_page": 1
  }
}
```

### Query Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `page` | integer | `1` | — | Page number (1-based) |
| `page_size` | integer | `25` | `100` | Results per page |

Unknown query parameters return 400. Duplicate parameters also return 400.

**Iterate all pages:**
```python
def all_pages(base_url, headers, **filters):
    page = 1
    while True:
        resp = requests.get(base_url, headers=headers, params={**filters, "page": page, "page_size": 100})
        resp.raise_for_status()
        body = resp.json()["data"]
        yield from body["projects"]  # or tasks, members, etc.
        if body["next_page"] is None:
            break
        page += 1
```

---

## Projects

### List projects (with filtering)

```bash
# All active projects
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/?status=active"

# Projects starting in 2026 Q1
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/?start_after=2026-01-01&start_before=2026-03-31"
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "projects": [
      {
        "id": 7,
        "name": "Portal Redesign",
        "description": "Full redesign of the customer portal.",
        "status": "active",
        "owner": {"id": 1, "name": "Alice Nguyen", "email": "alice@example.com"},
        "start_date": "2026-01-01",
        "due_date": "2026-06-30",
        "created_at": "2026-01-01T09:00:00+00:00"
      }
    ],
    "count": 1,
    "page": 1,
    "page_size": 25,
    "next_page": null,
    "previous_page": null
  }
}
```

### Get a single project

```bash
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/"
```

---

## Tasks

### List tasks with filters

```bash
# High-priority in-progress tasks assigned to user 2
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/tasks/?status=IN_PROGRESS&priority=high&assignee_id=2"

# Tasks in a specific sprint
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/tasks/?sprint=3"

# Tasks due this month
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/tasks/?due_after=2026-03-01&due_before=2026-03-31"
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "tasks": [
      {
        "id": 23,
        "project_id": 7,
        "title": "Implement login page",
        "description": "Build OAuth login UI.",
        "status": "IN_PROGRESS",
        "priority": "high",
        "assignee": {"id": 2, "name": "Bob Smith", "email": "bob@example.com"},
        "sprint_id": 3,
        "milestone_id": 1,
        "estimated_effort": "8.00",
        "actual_effort": "6.50",
        "due_date": "2026-03-15",
        "created_at": "2026-02-01T10:00:00+00:00",
        "updated_at": "2026-02-10T14:30:00+00:00"
      }
    ],
    "count": 1,
    "page": 1,
    "page_size": 25,
    "next_page": null,
    "previous_page": null
  }
}
```

### Create a task

```bash
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Implement login page", "priority": "high", "assignee_id": 2, "due_date": "2026-03-15"}' \
  "https://host/api/v1/projects/7/tasks/"
```

**Response `201 Created`:**
```json
{
  "status": "success",
  "message": "Task created successfully.",
  "data": {
    "id": 23,
    "project_id": 7,
    "title": "Implement login page",
    "status": "TODO",
    "priority": "high",
    "assignee": {"id": 2, "name": "Bob Smith", "email": "bob@example.com"},
    "sprint_id": null,
    "milestone_id": null,
    "estimated_effort": "0.00",
    "actual_effort": "0.00",
    "due_date": "2026-03-15",
    "created_at": "2026-02-01T10:00:00+00:00",
    "updated_at": "2026-02-01T10:00:00+00:00"
  }
}
```

### Update a task

```bash
curl -X PATCH \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"priority": "critical"}' \
  "https://host/api/v1/tasks/23/"
```

### Delete a task

```bash
curl -X DELETE \
  -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/tasks/23/"
```

---

## Task Status and Workflow

Status transitions are enforced by the project workflow. The default workflow:

```
TODO → IN_PROGRESS → REVIEW → DONE
                 ↑___________|
```

Tasks **must** pass through REVIEW before DONE can be set.

### Advance a task through the workflow

```bash
# Move to IN_PROGRESS
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "IN_PROGRESS"}' \
  "https://host/api/v1/tasks/23/status/"

# Move to REVIEW
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "REVIEW"}' \
  "https://host/api/v1/tasks/23/status/"

# Mark DONE (only allowed from REVIEW)
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "DONE"}' \
  "https://host/api/v1/tasks/23/status/"
```

**Attempting an invalid transition returns `400`:**
```json
{
  "status": "error",
  "message": "Transition from 'TODO' to 'DONE' is not permitted by project workflow rules.",
  "errors": {}
}
```

---

## Project Memberships

### List members (filtered by role)

```bash
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/members/?role=team_member"
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "members": [
      {
        "id": 12,
        "project_id": 7,
        "user": {"id": 2, "name": "Bob Smith", "email": "bob@example.com"},
        "role": "team_member",
        "joined_at": "2026-01-05T08:00:00+00:00"
      }
    ],
    "count": 1,
    "page": 1,
    "page_size": 25,
    "next_page": null,
    "previous_page": null
  }
}
```

### Add a member

```bash
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 5, "role": "team_member"}' \
  "https://host/api/v1/projects/7/members/"
```

### Update member role

```bash
curl -X PATCH \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "project_manager"}' \
  "https://host/api/v1/projects/7/members/12/"
```

### Remove a member

```bash
curl -X DELETE \
  -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/members/12/"
```

---

## Workflow Configuration

### Get current workflow

```bash
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/workflow/"
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "states": [
      {"key": "TODO", "name": "To Do", "is_initial": true, "is_final": false},
      {"key": "IN_PROGRESS", "name": "In Progress", "is_initial": false, "is_final": false},
      {"key": "REVIEW", "name": "In Review", "is_initial": false, "is_final": false},
      {"key": "DONE", "name": "Done", "is_initial": false, "is_final": true}
    ],
    "transitions": [
      {"from": "TODO", "to": "IN_PROGRESS"},
      {"from": "IN_PROGRESS", "to": "REVIEW"},
      {"from": "REVIEW", "to": "DONE"},
      {"from": "REVIEW", "to": "IN_PROGRESS"}
    ]
  }
}
```

### Configure a custom workflow

```bash
curl -X PUT \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "states": ["Backlog", "In Progress", "QA", "Released"],
    "initial_state": "Backlog",
    "final_state": "Released",
    "transitions": [
      {"from": "Backlog", "to": "In Progress"},
      {"from": "In Progress", "to": "QA"},
      {"from": "QA", "to": "Released"},
      {"from": "QA", "to": "In Progress"}
    ]
  }' \
  "https://host/api/v1/projects/7/workflow/configure/"
```

---

## Sprints

### List sprints (active only)

```bash
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/sprints/?status=active"
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "sprints": [
      {
        "id": 3,
        "name": "Sprint 1",
        "goal": "Complete login flow.",
        "status": "active",
        "start_date": "2026-02-01",
        "end_date": "2026-02-14",
        "task_count": 8
      }
    ],
    "count": 1,
    "page": 1,
    "page_size": 25,
    "next_page": null,
    "previous_page": null
  }
}
```

### Create a sprint

```bash
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sprint 2",
    "goal": "Dashboard and notifications.",
    "start_date": "2026-02-15",
    "end_date": "2026-02-28"
  }' \
  "https://host/api/v1/projects/7/sprints/"
```

### Update a sprint

```bash
curl -X PATCH \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "active", "goal": "Updated sprint goal."}' \
  "https://host/api/v1/projects/7/sprints/3/"
```

---

## Milestones

### List milestones (with date range filter)

```bash
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/milestones/?target_after=2026-03-01&target_before=2026-06-30"
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "milestones": [
      {
        "id": 1,
        "name": "Alpha Release",
        "description": "Internal alpha with core features.",
        "target_date": "2026-03-01",
        "task_count": 12
      }
    ],
    "count": 1,
    "page": 1,
    "page_size": 25,
    "next_page": null,
    "previous_page": null
  }
}
```

### Create a milestone

```bash
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Beta Release", "description": "Public beta.", "target_date": "2026-05-01"}' \
  "https://host/api/v1/projects/7/milestones/"
```

---

## Task Comments

### List comments

```bash
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/tasks/23/comments/"
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "comments": [
      {
        "id": 55,
        "task_id": 23,
        "author": {"id": 1, "name": "Alice Nguyen"},
        "content": "LGTM, merging.",
        "created_at": "2026-02-10T14:00:00+00:00"
      }
    ],
    "count": 1,
    "page": 1,
    "page_size": 25,
    "next_page": null,
    "previous_page": null
  }
}
```

### Add a comment

```bash
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Reviewed — looks good!"}' \
  "https://host/api/v1/projects/7/tasks/23/comments/"
```

### Edit a comment

```bash
curl -X PATCH \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Updated comment text."}' \
  "https://host/api/v1/projects/7/tasks/23/comments/55/"
```

### Delete a comment

```bash
curl -X DELETE \
  -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/tasks/23/comments/55/"
```

---

## Project Reports

### Get project report

```bash
curl -H "Authorization: Bearer TOKEN" \
  "https://host/api/v1/projects/7/reports/"
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "project_id": 7,
    "progress": {
      "total_tasks": 20,
      "completed_tasks": 8,
      "in_progress_tasks": 5,
      "overdue_tasks": 2,
      "completion_percentage": "40.00"
    },
    "velocity": {
      "sprints": [
        {
          "name": "Sprint 1",
          "status": "completed",
          "total_tasks": 10,
          "completed_tasks": 8,
          "estimated_effort": "80.00",
          "completed_effort": "72.00",
          "velocity": "72.00",
          "is_closed": true
        }
      ],
      "closed_sprint_count": 1,
      "complete_velocity_sprint_count": 1,
      "incomplete_sprint_count": 0,
      "total_completed_effort": "72.00",
      "average_velocity": "72.00"
    },
    "workload": [
      {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "total_tasks": 6,
        "active_tasks": 3,
        "completed_tasks": 3,
        "estimated_effort": "48.00",
        "actual_effort": "36.00"
      }
    ]
  }
}
```

---

## Endpoint Quick Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/projects/` | List visible projects |
| GET | `/api/v1/projects/{id}/` | Get project detail |
| GET | `/api/v1/projects/{id}/tasks/` | List tasks (filterable, paginated) |
| POST | `/api/v1/projects/{id}/tasks/` | Create task |
| GET | `/api/v1/tasks/{id}/` | Get task detail |
| PATCH | `/api/v1/tasks/{id}/` | Update task fields |
| DELETE | `/api/v1/tasks/{id}/` | Delete task |
| POST | `/api/v1/tasks/{id}/status/` | Transition task status |
| GET | `/api/v1/projects/{id}/members/` | List members |
| POST | `/api/v1/projects/{id}/members/` | Add member |
| PATCH | `/api/v1/projects/{id}/members/{mid}/` | Update member role |
| DELETE | `/api/v1/projects/{id}/members/{mid}/` | Remove member |
| GET | `/api/v1/projects/{id}/workflow/` | Get workflow |
| PUT | `/api/v1/projects/{id}/workflow/configure/` | Configure workflow |
| GET | `/api/v1/projects/{id}/sprints/` | List sprints |
| POST | `/api/v1/projects/{id}/sprints/` | Create sprint |
| GET | `/api/v1/projects/{id}/sprints/{sid}/` | Get sprint |
| PATCH | `/api/v1/projects/{id}/sprints/{sid}/` | Update sprint |
| DELETE | `/api/v1/projects/{id}/sprints/{sid}/` | Delete sprint |
| GET | `/api/v1/projects/{id}/milestones/` | List milestones |
| POST | `/api/v1/projects/{id}/milestones/` | Create milestone |
| GET | `/api/v1/projects/{id}/tasks/{tid}/comments/` | List comments |
| POST | `/api/v1/projects/{id}/tasks/{tid}/comments/` | Add comment |
| PATCH | `/api/v1/projects/{id}/tasks/{tid}/comments/{cid}/` | Edit comment |
| DELETE | `/api/v1/projects/{id}/tasks/{tid}/comments/{cid}/` | Delete comment |
| GET | `/api/v1/projects/{id}/reports/` | Get project reports |
| GET | `/api/v1/openapi.json` | Download OpenAPI 3.0 spec |
| GET | `/api/v1/docs/` | Browse interactive API docs |
