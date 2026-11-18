from django.http import JsonResponse
from django.shortcuts import render

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Project Management System REST API",
        "version": "1.0.0",
        "description": "Comprehensive REST API for project tracking, task workflows, sprint planning, and external integrations.",
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer"},
            "sessionAuth": {"type": "apiKey", "in": "cookie", "name": "sessionid"},
        }
    },
    "security": [{"bearerAuth": []}, {"sessionAuth": []}],
    "paths": {
        "/api/v1/projects/": {
            "get": {
                "summary": "List visible projects",
                "responses": {"200": {"description": "List of projects."}}
            }
        },
        "/api/v1/projects/{project_id}/": {
            "get": {
                "summary": "Get project details",
                "parameters": [{"name": "project_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {"200": {"description": "Project detail."}}
            }
        },
        "/api/v1/projects/{project_id}/tasks/": {
            "get": {
                "summary": "List tasks in project",
                "parameters": [{"name": "project_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {"200": {"description": "Task list."}}
            },
            "post": {
                "summary": "Create new task",
                "responses": {"201": {"description": "Task created."}}
            }
        },
        "/api/v1/tasks/{task_id}/status/": {
            "post": {
                "summary": "Update task status with workflow enforcement",
                "parameters": [{"name": "task_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "responses": {"200": {"description": "Status updated."}}
            }
        },
        "/api/v1/projects/{project_id}/members/": {
            "get": {"summary": "List project members", "responses": {"200": {"description": "Membership list."}}},
            "post": {"summary": "Add project member", "responses": {"201": {"description": "Member added."}, "400": {"description": "Invalid payload."}, "403": {"description": "Permission denied."}}}
        },
        "/api/v1/projects/{project_id}/members/{membership_id}/": {
            "patch": {"summary": "Update member role", "responses": {"200": {"description": "Role updated."}, "403": {"description": "Permission denied."}}},
            "delete": {"summary": "Remove project member", "responses": {"200": {"description": "Member removed."}, "400": {"description": "Owner or invalid state."}}}
        },
        "/api/v1/projects/{project_id}/workflow/": {
            "get": {"summary": "Retrieve project workflow configuration", "responses": {"200": {"description": "Workflow states and transitions."}}}
        },
        "/api/v1/projects/{project_id}/workflow/configure/": {
            "put": {"summary": "Create or replace project workflow", "responses": {"200": {"description": "Workflow updated."}, "400": {"description": "Invalid states or transitions."}, "403": {"description": "Permission denied."}}}
        },
        "/api/v1/projects/{project_id}/sprints/": {
            "get": {"summary": "List project sprints", "responses": {"200": {"description": "Sprint list."}}},
            "post": {"summary": "Create sprint", "responses": {"201": {"description": "Sprint created."}, "400": {"description": "Invalid payload."}}}
        },
        "/api/v1/projects/{project_id}/sprints/{sprint_id}/": {
            "get": {"summary": "Retrieve sprint", "responses": {"200": {"description": "Sprint detail."}}},
            "patch": {"summary": "Update sprint", "responses": {"200": {"description": "Sprint updated."}}},
            "delete": {"summary": "Delete sprint", "responses": {"200": {"description": "Sprint deleted."}, "400": {"description": "Sprint has assigned tasks."}}}
        },
        "/api/v1/projects/{project_id}/milestones/": {
            "get": {"summary": "List project milestones", "responses": {"200": {"description": "Milestone list."}}},
            "post": {"summary": "Create milestone", "responses": {"201": {"description": "Milestone created."}, "400": {"description": "Invalid payload."}}}
        },
        "/api/v1/projects/{project_id}/milestones/{milestone_id}/": {
            "get": {"summary": "Retrieve milestone", "responses": {"200": {"description": "Milestone detail."}}},
            "patch": {"summary": "Update milestone", "responses": {"200": {"description": "Milestone updated."}}},
            "delete": {"summary": "Delete milestone", "responses": {"200": {"description": "Milestone deleted."}, "400": {"description": "Milestone has assigned tasks."}}}
        },
        "/api/v1/projects/{project_id}/tasks/{task_id}/comments/": {
            "get": {"summary": "List task comments", "responses": {"200": {"description": "Comment list."}}},
            "post": {"summary": "Create task comment", "responses": {"201": {"description": "Comment created."}, "400": {"description": "Invalid payload."}}}
        },
        "/api/v1/projects/{project_id}/tasks/{task_id}/comments/{comment_id}/": {
            "patch": {"summary": "Update owned task comment", "responses": {"200": {"description": "Comment updated."}, "403": {"description": "Permission denied."}}},
            "delete": {"summary": "Delete task comment", "responses": {"200": {"description": "Comment deleted."}, "403": {"description": "Permission denied."}}}
        },
        "/api/v1/projects/{project_id}/reports/": {
            "get": {"summary": "Retrieve project progress, velocity, and workload reports", "responses": {"200": {"description": "Structured JSON report."}, "404": {"description": "Project not found or access denied."}}}
        },
    }
}


def openapi_spec_api(request):
    return JsonResponse(OPENAPI_SPEC)


def api_docs_viewer(request):
    return render(request, "api_docs.html", {"spec": OPENAPI_SPEC})
