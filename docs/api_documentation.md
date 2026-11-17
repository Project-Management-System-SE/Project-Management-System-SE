# REST API and External Integration Guide

## Overview
The REST API provides programmatic access to projects, tasks, workflow transitions, sprints, and milestones. External automation systems such as GitHub Actions, Slack notification bots, and email sync scripts integrate seamlessly via API Token authentication.

---

## Authentication
The token API accepts standard Bearer or Token headers. Valid tokens are required for
state-changing requests:
```bash
curl -X POST https://example.com/api/v1/projects/42/tasks/ \
     -H "Authorization: Bearer <your_api_token>" \
     -H "Content-Type: application/json" \
     -d '{"title": "New task"}'
```
Authenticated Django sessions may use its safe `GET` endpoints. For session-authenticated
project/task reads and writes, use `/api/v1/session/`; its unsafe requests require Django's
normal CSRF token. Both APIs enforce project visibility and task permissions.

---

## Endpoints Reference

### Projects
- `GET /api/v1/projects/`: List all visible projects.
- `GET /api/v1/projects/{project_id}/`: Retrieve detailed project metadata.

### Tasks
- `GET /api/v1/projects/{project_id}/tasks/`: Query tasks with optional `?status=...&priority=...` filters.
- `POST /api/v1/projects/{project_id}/tasks/`: Create a task.
- `GET /api/v1/tasks/{task_id}/`: Retrieve task details.
- `PATCH /api/v1/tasks/{task_id}/`: Update task fields.
- `POST /api/v1/tasks/{task_id}/status/`: Transition task status (strictly enforces project workflow rules).
- `DELETE /api/v1/tasks/{task_id}/`: Delete a task (requires Project Manager privileges).

### Sprints & Milestones
- `GET /api/v1/projects/{project_id}/sprints/`: List project sprints.
- `GET /api/v1/projects/{project_id}/milestones/`: List project milestones.

---

## External Integrations

### 1. GitHub Actions Integration
GitHub Actions workflows can automatically create tasks or update task status when pull requests are merged:
```yaml
name: Sync Task on PR Merge
on:
  pull_request:
    types: [closed]
jobs:
  sync-task:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Update Task Status
        run: |
          curl -X POST https://example.com/api/v1/tasks/42/status/ \
               -H "Authorization: Bearer ${{ secrets.PMS_API_TOKEN }}" \
               -H "Content-Type: application/json" \
               -d '{"status": "DONE"}'
```

### 2. Slack Notification Integration
Outbound webhooks or bot integrations can notify channels whenever high-priority tasks are created or workflow transitions are blocked.

### 3. Email Alerts
Automated nightly digest scripts query `/api/v1/projects/{id}/tasks/` for overdue tasks and deliver summary alerts to project managers.
