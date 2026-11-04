from django.http import JsonResponse
from django.shortcuts import render

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Project Management System REST API",
        "version": "1.0.0",
        "description": "Comprehensive REST API for project tracking, task workflows, sprint planning, and external integrations.",
    },
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
        }
    }
}


def openapi_spec_api(request):
    return JsonResponse(OPENAPI_SPEC)


def api_docs_viewer(request):
    return render(request, "api_docs.html", {"spec": OPENAPI_SPEC})
