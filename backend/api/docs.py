"""
API documentation: OpenAPI 3.0 specification with request/response examples,
authentication notes, pagination and filtering reference, throttling guidance,
and standardised error response shapes.
"""
from django.http import JsonResponse
from django.shortcuts import render

# ---------------------------------------------------------------------------
# Shared schema components
# ---------------------------------------------------------------------------

_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "example": "error"},
        "message": {"type": "string", "example": "A human-readable error description."},
        "errors": {
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
            "example": {"field_name": ["Validation message."]},
        },
    },
    "required": ["status", "message", "errors"],
}

_SUCCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "example": "success"},
        "data": {"type": "object"},
    },
    "required": ["status", "data"],
}

_PAGINATION_PARAMS = [
    {
        "name": "page",
        "in": "query",
        "required": False,
        "schema": {"type": "integer", "default": 1, "minimum": 1},
        "description": "Page number (1-based).",
        "example": 2,
    },
    {
        "name": "page_size",
        "in": "query",
        "required": False,
        "schema": {"type": "integer", "default": 25, "minimum": 1, "maximum": 100},
        "description": "Number of results per page (1–100).",
        "example": 10,
    },
]

_PAGINATION_METADATA = {
    "count": {"type": "integer", "description": "Total number of matching records.", "example": 42},
    "page": {"type": "integer", "description": "Current page number.", "example": 2},
    "page_size": {"type": "integer", "description": "Records returned on this page.", "example": 10},
    "next_page": {"type": ["integer", "null"], "description": "Next page number, or null.", "example": 3},
    "previous_page": {"type": ["integer", "null"], "description": "Previous page number, or null.", "example": 1},
}

_PATH_PROJECT_ID = {
    "name": "project_id",
    "in": "path",
    "required": True,
    "schema": {"type": "integer"},
    "description": "Primary key of the project.",
    "example": 7,
}
_PATH_TASK_ID = {
    "name": "task_id",
    "in": "path",
    "required": True,
    "schema": {"type": "integer"},
    "description": "Primary key of the task.",
    "example": 23,
}

# ---------------------------------------------------------------------------
# Shared response objects
# ---------------------------------------------------------------------------

_RESPONSE_401 = {
    "description": "Authentication required.",
    "content": {
        "application/json": {
            "schema": _ERROR_SCHEMA,
            "example": {
                "status": "error",
                "message": "Authentication required. Provide a valid Bearer token or session.",
                "errors": {},
            },
        }
    },
}
_RESPONSE_403 = {
    "description": "Permission denied.",
    "content": {
        "application/json": {
            "schema": _ERROR_SCHEMA,
            "example": {
                "status": "error",
                "message": "You do not have permission to perform this action.",
                "errors": {},
            },
        }
    },
}
_RESPONSE_404 = {
    "description": "Resource not found or not visible to the caller.",
    "content": {
        "application/json": {
            "schema": _ERROR_SCHEMA,
            "example": {
                "status": "error",
                "message": "Project not found or access denied.",
                "errors": {},
            },
        }
    },
}
_RESPONSE_422 = {
    "description": "Validation error – the request body failed field-level validation.",
    "content": {
        "application/json": {
            "schema": _ERROR_SCHEMA,
            "example": {
                "status": "error",
                "message": "Task validation failed.",
                "errors": {
                    "title": ["Ensure this field has at least 3 characters."],
                    "due_date": ["Enter a valid date."],
                },
            },
        }
    },
}
_RESPONSE_429 = {
    "description": "Rate limit exceeded.",
    "headers": {
        "Retry-After": {
            "description": "Seconds to wait before retrying.",
            "schema": {"type": "integer"},
            "example": 60,
        }
    },
    "content": {
        "application/json": {
            "schema": _ERROR_SCHEMA,
            "example": {
                "status": "error",
                "message": "API rate limit exceeded. Try again later.",
                "errors": {"rate_limit": ["Request limit exceeded."]},
            },
        }
    },
}

# ---------------------------------------------------------------------------
# Project schemas
# ---------------------------------------------------------------------------

_PROJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 7},
        "name": {"type": "string", "example": "Portal Redesign"},
        "description": {"type": "string", "example": "Full redesign of the customer portal."},
        "status": {
            "type": "string",
            "enum": ["active", "on_hold", "completed", "archived"],
            "example": "active",
        },
        "owner": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "name": {"type": "string", "example": "Alice Nguyen"},
                "email": {"type": "string", "format": "email", "example": "alice@example.com"},
            },
        },
        "start_date": {"type": ["string", "null"], "format": "date", "example": "2026-01-01"},
        "due_date": {"type": ["string", "null"], "format": "date", "example": "2026-06-30"},
        "created_at": {"type": ["string", "null"], "format": "date-time"},
    },
}

_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 23},
        "project_id": {"type": "integer", "example": 7},
        "title": {"type": "string", "example": "Implement login page"},
        "description": {"type": "string", "example": "Build the new login UI with OAuth support."},
        "status": {"type": "string", "example": "TODO"},
        "priority": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
            "example": "high",
        },
        "assignee": {
            "type": ["object", "null"],
            "properties": {
                "id": {"type": "integer", "example": 2},
                "name": {"type": "string", "example": "Bob Smith"},
                "email": {"type": "string", "format": "email", "example": "bob@example.com"},
            },
        },
        "sprint_id": {"type": ["integer", "null"], "example": 3},
        "milestone_id": {"type": ["integer", "null"], "example": 1},
        "estimated_effort": {"type": "string", "example": "8.00"},
        "actual_effort": {"type": "string", "example": "6.50"},
        "due_date": {"type": ["string", "null"], "format": "date", "example": "2026-03-15"},
        "created_at": {"type": ["string", "null"], "format": "date-time"},
        "updated_at": {"type": ["string", "null"], "format": "date-time"},
    },
}

_MEMBERSHIP_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 12},
        "project_id": {"type": "integer", "example": 7},
        "user": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 2},
                "name": {"type": "string", "example": "Bob Smith"},
                "email": {"type": "string", "format": "email", "example": "bob@example.com"},
            },
        },
        "role": {
            "type": "string",
            "enum": ["project_manager", "team_member"],
            "example": "team_member",
        },
        "joined_at": {"type": "string", "format": "date-time"},
    },
}

_SPRINT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 3},
        "name": {"type": "string", "example": "Sprint 1"},
        "goal": {"type": "string", "example": "Complete login and registration flows."},
        "status": {
            "type": "string",
            "enum": ["planned", "active", "completed"],
            "example": "active",
        },
        "start_date": {"type": "string", "format": "date", "example": "2026-02-01"},
        "end_date": {"type": "string", "format": "date", "example": "2026-02-14"},
        "task_count": {"type": "integer", "example": 8},
    },
}

_MILESTONE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 1},
        "name": {"type": "string", "example": "Alpha Release"},
        "description": {"type": "string", "example": "Internal alpha with core features."},
        "target_date": {"type": ["string", "null"], "format": "date", "example": "2026-03-01"},
        "status": {
            "type": "string",
            "enum": ["planned", "in_progress", "completed", "cancelled"],
            "example": "planned",
        },
        "task_count": {"type": "integer", "example": 12},
    },
}

_COMMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 55},
        "task_id": {"type": "integer", "example": 23},
        "author": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "name": {"type": "string", "example": "Alice Nguyen"},
            },
        },
        "content": {"type": "string", "example": "Reviewed — looks good, merging."},
        "created_at": {"type": "string", "format": "date-time"},
    },
}

# ---------------------------------------------------------------------------
# Full OpenAPI specification
# ---------------------------------------------------------------------------

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Project Management System REST API",
        "version": "1.0.0",
        "description": (
            "REST API for project tracking, task workflows, sprint planning, and external integrations.\n\n"
            "## Authentication\n"
            "All endpoints require authentication. Two schemes are supported:\n\n"
            "1. **Bearer token** – obtain an API token via the admin or account settings and pass it as "
            "`Authorization: Bearer <token>`. Supported for both safe and unsafe methods.\n"
            "2. **Session cookie** – log in through the web UI; the browser sends the `sessionid` cookie "
            "automatically. Session authentication is accepted for all GET requests and for the legacy "
            "`/api/v1/session/` endpoints. Unsafe requests on `api/v1/` endpoints require a Bearer token.\n\n"
            "## Rate Limiting\n"
            "Throttling is applied per authenticated user (or per IP for anonymous callers):\n\n"
            "- **Read requests** (GET / HEAD): 60 requests per 60-second window (default).\n"
            "- **Write requests** (POST / PATCH / PUT / DELETE): 20 requests per 60-second window (default).\n\n"
            "When the limit is exceeded the API returns `429 Too Many Requests` with a `Retry-After` header "
            "containing the number of seconds to wait.\n\n"
            "## Pagination\n"
            "List endpoints return paginated results. Use `?page=N&page_size=M` (page_size 1–100, default 25). "
            "The response envelope always includes `count`, `page`, `page_size`, `next_page`, and "
            "`previous_page`.\n\n"
            "## Error Responses\n"
            "All error responses share the same JSON envelope:\n"
            "```json\n"
            '{"status": "error", "message": "...", "errors": {"field": ["message"]}}\n'
            "```\n"
            "HTTP status codes: 400 (validation), 401 (unauthenticated), 403 (forbidden), "
            "404 (not found), 405 (method not allowed), 415 (bad content-type), 429 (rate limited).\n\n"
            "## Workflow Enforcement\n"
            "Task status transitions are validated against the project workflow. The default workflow "
            "requires tasks to pass through REVIEW before reaching DONE. Custom workflows are configured "
            "per-project. Invalid transitions return 400."
        ),
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "API token obtained from account settings. Pass as `Authorization: Bearer <token>`.",
            },
            "sessionAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "sessionid",
                "description": "Django session cookie. Obtained by logging in via the web UI.",
            },
        },
        "schemas": {
            "Error": _ERROR_SCHEMA,
            "Success": _SUCCESS_SCHEMA,
            "Project": _PROJECT_SCHEMA,
            "Task": _TASK_SCHEMA,
            "Membership": _MEMBERSHIP_SCHEMA,
            "Sprint": _SPRINT_SCHEMA,
            "Milestone": _MILESTONE_SCHEMA,
            "Comment": _COMMENT_SCHEMA,
        },
        "responses": {
            "Unauthorized": _RESPONSE_401,
            "Forbidden": _RESPONSE_403,
            "NotFound": _RESPONSE_404,
            "ValidationError": _RESPONSE_422,
            "TooManyRequests": _RESPONSE_429,
        },
    },
    "security": [{"bearerAuth": []}, {"sessionAuth": []}],
    "paths": {
        # ------------------------------------------------------------------ #
        # Projects
        # ------------------------------------------------------------------ #
        "/api/v1/projects/": {
            "get": {
                "summary": "List visible projects",
                "operationId": "listProjects",
                "tags": ["Projects"],
                "description": (
                    "Returns all projects visible to the authenticated user (owned or member-of). "
                    "Supports filtering by status and date ranges, and pagination."
                ),
                "parameters": [
                    *_PAGINATION_PARAMS,
                    {
                        "name": "status",
                        "in": "query",
                        "required": False,
                        "schema": {
                            "type": "string",
                            "enum": ["active", "on_hold", "completed", "archived"],
                        },
                        "description": "Filter by project status.",
                        "example": "active",
                    },
                    {
                        "name": "start_after",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Include only projects with start_date >= this value (YYYY-MM-DD).",
                        "example": "2026-01-01",
                    },
                    {
                        "name": "start_before",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Include only projects with start_date <= this value (YYYY-MM-DD).",
                        "example": "2026-12-31",
                    },
                    {
                        "name": "due_after",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Include only projects with due_date >= this value (YYYY-MM-DD).",
                        "example": "2026-06-01",
                    },
                    {
                        "name": "due_before",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Include only projects with due_date <= this value (YYYY-MM-DD).",
                        "example": "2026-12-31",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Paginated list of projects.",
                        "content": {
                            "application/json": {
                                "example": {
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
                                                "created_at": "2026-01-01T09:00:00+00:00",
                                            }
                                        ],
                                        "count": 1,
                                        "page": 1,
                                        "page_size": 25,
                                        "next_page": None,
                                        "previous_page": None,
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "400": {
                        "description": "Invalid filter parameters.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "error",
                                    "message": "Invalid project status.",
                                    "errors": {"status": ["Choose a valid project status."]},
                                }
                            }
                        },
                    },
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            }
        },
        "/api/v1/projects/{project_id}/": {
            "get": {
                "summary": "Get project details",
                "operationId": "getProject",
                "tags": ["Projects"],
                "parameters": [_PATH_PROJECT_ID],
                "responses": {
                    "200": {
                        "description": "Project detail.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "id": 7,
                                        "name": "Portal Redesign",
                                        "description": "Full redesign.",
                                        "status": "active",
                                        "owner": {"id": 1, "name": "Alice Nguyen", "email": "alice@example.com"},
                                        "start_date": "2026-01-01",
                                        "due_date": "2026-06-30",
                                        "created_at": "2026-01-01T09:00:00+00:00",
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            }
        },
        # ------------------------------------------------------------------ #
        # Tasks
        # ------------------------------------------------------------------ #
        "/api/v1/projects/{project_id}/tasks/": {
            "get": {
                "summary": "List tasks in a project",
                "operationId": "listTasks",
                "tags": ["Tasks"],
                "description": (
                    "Returns paginated tasks for the given project. Supports filtering by status, "
                    "priority, assignee, sprint, milestone, and created/due date ranges."
                ),
                "parameters": [
                    _PATH_PROJECT_ID,
                    *_PAGINATION_PARAMS,
                    {
                        "name": "status",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "Workflow status key (e.g. TODO, IN_PROGRESS, REVIEW, DONE).",
                        "example": "IN_PROGRESS",
                    },
                    {
                        "name": "priority",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "description": "Task priority level.",
                        "example": "high",
                    },
                    {
                        "name": "assignee_id",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                        "description": "Filter by assignee user ID.",
                        "example": 2,
                    },
                    {
                        "name": "sprint",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                        "description": "Filter by sprint ID (must belong to this project).",
                        "example": 3,
                    },
                    {
                        "name": "milestone",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                        "description": "Filter by milestone ID (must belong to this project).",
                        "example": 1,
                    },
                    {
                        "name": "created_after",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Include only tasks created on or after this date (YYYY-MM-DD).",
                        "example": "2026-02-01",
                    },
                    {
                        "name": "created_before",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Include only tasks created on or before this date (YYYY-MM-DD).",
                        "example": "2026-02-28",
                    },
                    {
                        "name": "due_after",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Include only tasks with due_date >= this value.",
                        "example": "2026-03-01",
                    },
                    {
                        "name": "due_before",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Include only tasks with due_date <= this value.",
                        "example": "2026-03-31",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Paginated task list.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "tasks": [
                                            {
                                                "id": 23,
                                                "project_id": 7,
                                                "title": "Implement login page",
                                                "description": "OAuth login UI.",
                                                "status": "IN_PROGRESS",
                                                "priority": "high",
                                                "assignee": {"id": 2, "name": "Bob Smith", "email": "bob@example.com"},
                                                "sprint_id": 3,
                                                "milestone_id": 1,
                                                "estimated_effort": "8.00",
                                                "actual_effort": "6.50",
                                                "due_date": "2026-03-15",
                                                "created_at": "2026-02-01T10:00:00+00:00",
                                                "updated_at": "2026-02-10T14:30:00+00:00",
                                            }
                                        ],
                                        "count": 1,
                                        "page": 1,
                                        "page_size": 25,
                                        "next_page": None,
                                        "previous_page": None,
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Invalid filter parameters.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "error",
                                    "message": "Invalid task status.",
                                    "errors": {"status": ["Choose a valid workflow status."]},
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "post": {
                "summary": "Create a new task",
                "operationId": "createTask",
                "tags": ["Tasks"],
                "description": "Creates a task in the given project. Requires project membership.",
                "parameters": [_PATH_PROJECT_ID],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["title"],
                                "properties": {
                                    "title": {"type": "string", "minLength": 3, "example": "Implement login page"},
                                    "description": {"type": "string", "example": "Build OAuth login UI."},
                                    "priority": {
                                        "type": "string",
                                        "enum": ["low", "medium", "high", "critical"],
                                        "default": "medium",
                                        "example": "high",
                                    },
                                    "assignee_id": {"type": "integer", "nullable": True, "example": 2},
                                    "due_date": {"type": "string", "format": "date", "example": "2026-03-15"},
                                },
                            },
                            "example": {
                                "title": "Implement login page",
                                "description": "Build OAuth login UI.",
                                "priority": "high",
                                "assignee_id": 2,
                                "due_date": "2026-03-15",
                            },
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Task created successfully.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "message": "Task created successfully.",
                                    "data": {
                                        "id": 23,
                                        "project_id": 7,
                                        "title": "Implement login page",
                                        "description": "Build OAuth login UI.",
                                        "status": "TODO",
                                        "priority": "high",
                                        "assignee": {"id": 2, "name": "Bob Smith", "email": "bob@example.com"},
                                        "sprint_id": None,
                                        "milestone_id": None,
                                        "estimated_effort": "0.00",
                                        "actual_effort": "0.00",
                                        "due_date": "2026-03-15",
                                        "created_at": "2026-02-01T10:00:00+00:00",
                                        "updated_at": "2026-02-01T10:00:00+00:00",
                                    },
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "415": {
                        "description": "Unsupported media type – Content-Type must be application/json.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "error",
                                    "message": "Content-Type must be application/json.",
                                    "errors": {},
                                }
                            }
                        },
                    },
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        "/api/v1/tasks/{task_id}/": {
            "get": {
                "summary": "Retrieve a task",
                "operationId": "getTask",
                "tags": ["Tasks"],
                "parameters": [_PATH_TASK_ID],
                "responses": {
                    "200": {
                        "description": "Task detail.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "id": 23,
                                        "project_id": 7,
                                        "title": "Implement login page",
                                        "status": "IN_PROGRESS",
                                        "priority": "high",
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "patch": {
                "summary": "Update task fields",
                "operationId": "updateTask",
                "tags": ["Tasks"],
                "description": (
                    "Partially updates title, description, priority, or assignee_id. "
                    "Reassigning requires project-manager permission. "
                    "To change status use `POST /api/v1/tasks/{task_id}/status/`."
                ),
                "parameters": [_PATH_TASK_ID],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string", "minLength": 3},
                                    "description": {"type": "string"},
                                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                                    "assignee_id": {"type": ["integer", "null"]},
                                },
                            },
                            "example": {"priority": "critical", "assignee_id": 3},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Task updated.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "message": "Task updated successfully.",
                                    "data": {"id": 23, "priority": "critical"},
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "delete": {
                "summary": "Delete a task",
                "operationId": "deleteTask",
                "tags": ["Tasks"],
                "parameters": [_PATH_TASK_ID],
                "responses": {
                    "200": {
                        "description": "Task deleted.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "message": "Task deleted successfully.",
                                    "data": {"deleted_task_id": 23},
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        "/api/v1/tasks/{task_id}/status/": {
            "post": {
                "summary": "Update task status (workflow-enforced)",
                "operationId": "updateTaskStatus",
                "tags": ["Tasks"],
                "description": (
                    "Transitions a task to a new workflow status. The transition must be allowed "
                    "by the project workflow. The default workflow requires passing through REVIEW "
                    "before DONE can be set. Returns 400 if the transition is invalid."
                ),
                "parameters": [_PATH_TASK_ID],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["status"],
                                "properties": {"status": {"type": "string", "example": "IN_PROGRESS"}},
                            },
                            "example": {"status": "REVIEW"},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Status updated successfully.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "message": "Task status updated successfully.",
                                    "data": {"id": 23, "status": "REVIEW"},
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Invalid transition.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "error",
                                    "message": "Transition from 'TODO' to 'DONE' is not permitted by project workflow rules.",
                                    "errors": {},
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            }
        },
        # ------------------------------------------------------------------ #
        # Memberships
        # ------------------------------------------------------------------ #
        "/api/v1/projects/{project_id}/members/": {
            "get": {
                "summary": "List project members",
                "operationId": "listMembers",
                "tags": ["Memberships"],
                "parameters": [
                    _PATH_PROJECT_ID,
                    *_PAGINATION_PARAMS,
                    {
                        "name": "role",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["project_manager", "team_member"]},
                        "description": "Filter by membership role.",
                        "example": "team_member",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Paginated membership list.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "members": [
                                            {
                                                "id": 12,
                                                "project_id": 7,
                                                "user": {"id": 2, "name": "Bob Smith", "email": "bob@example.com"},
                                                "role": "team_member",
                                                "joined_at": "2026-01-05T08:00:00+00:00",
                                            }
                                        ],
                                        "count": 1,
                                        "page": 1,
                                        "page_size": 25,
                                        "next_page": None,
                                        "previous_page": None,
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "post": {
                "summary": "Add a project member",
                "operationId": "addMember",
                "tags": ["Memberships"],
                "description": "Adds a user as a project member. Requires project-manager permission.",
                "parameters": [_PATH_PROJECT_ID],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["user_id", "role"],
                                "properties": {
                                    "user_id": {"type": "integer", "example": 2},
                                    "role": {
                                        "type": "string",
                                        "enum": ["project_manager", "team_member"],
                                        "example": "team_member",
                                    },
                                },
                            },
                            "example": {"user_id": 2, "role": "team_member"},
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Member added.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "message": "Project member added successfully.",
                                    "data": {
                                        "id": 12,
                                        "project_id": 7,
                                        "user": {"id": 2, "name": "Bob Smith", "email": "bob@example.com"},
                                        "role": "team_member",
                                        "joined_at": "2026-01-05T08:00:00+00:00",
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Duplicate member or missing fields.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "error",
                                    "message": "This user is already a project member.",
                                    "errors": {},
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        "/api/v1/projects/{project_id}/members/{membership_id}/": {
            "patch": {
                "summary": "Update member role",
                "operationId": "updateMember",
                "tags": ["Memberships"],
                "parameters": [
                    _PATH_PROJECT_ID,
                    {"name": "membership_id", "in": "path", "required": True, "schema": {"type": "integer"}, "example": 12},
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "example": {"role": "project_manager"},
                        }
                    },
                },
                "responses": {
                    "200": {"description": "Role updated.", "content": {"application/json": {"example": {"status": "success", "message": "Project member role updated successfully.", "data": {"id": 12, "role": "project_manager"}}}}},
                    "400": {"description": "Cannot change owner or invalid role.", "content": {"application/json": {"example": {"status": "error", "message": "The project owner's membership cannot be changed or removed.", "errors": {}}}}},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "delete": {
                "summary": "Remove a project member",
                "operationId": "removeMember",
                "tags": ["Memberships"],
                "parameters": [
                    _PATH_PROJECT_ID,
                    {"name": "membership_id", "in": "path", "required": True, "schema": {"type": "integer"}, "example": 12},
                ],
                "responses": {
                    "200": {"description": "Member removed.", "content": {"application/json": {"example": {"status": "success", "message": "Project member removed successfully.", "data": {"deleted_membership_id": 12}}}}},
                    "400": {"description": "Cannot remove project owner.", "content": {"application/json": {"example": {"status": "error", "message": "The project owner's membership cannot be changed or removed.", "errors": {}}}}},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        # ------------------------------------------------------------------ #
        # Workflow
        # ------------------------------------------------------------------ #
        "/api/v1/projects/{project_id}/workflow/": {
            "get": {
                "summary": "Retrieve project workflow configuration",
                "operationId": "getWorkflow",
                "tags": ["Workflow"],
                "description": "Returns the states and allowed transitions for the project workflow.",
                "parameters": [_PATH_PROJECT_ID],
                "responses": {
                    "200": {
                        "description": "Workflow states and transitions.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "states": [
                                            {"key": "TODO", "name": "To Do", "is_initial": True, "is_final": False},
                                            {"key": "IN_PROGRESS", "name": "In Progress", "is_initial": False, "is_final": False},
                                            {"key": "REVIEW", "name": "In Review", "is_initial": False, "is_final": False},
                                            {"key": "DONE", "name": "Done", "is_initial": False, "is_final": True},
                                        ],
                                        "transitions": [
                                            {"from": "TODO", "to": "IN_PROGRESS"},
                                            {"from": "IN_PROGRESS", "to": "REVIEW"},
                                            {"from": "REVIEW", "to": "DONE"},
                                            {"from": "REVIEW", "to": "IN_PROGRESS"},
                                        ],
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            }
        },
        "/api/v1/projects/{project_id}/workflow/configure/": {
            "put": {
                "summary": "Create or replace project workflow",
                "operationId": "configureWorkflow",
                "tags": ["Workflow"],
                "description": "Replaces the project's workflow configuration. Requires project-manager permission.",
                "parameters": [_PATH_PROJECT_ID],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "example": {
                                "states": ["Backlog", "In Progress", "QA", "Released"],
                                "initial_state": "Backlog",
                                "final_state": "Released",
                                "transitions": [
                                    {"from": "Backlog", "to": "In Progress"},
                                    {"from": "In Progress", "to": "QA"},
                                    {"from": "QA", "to": "Released"},
                                    {"from": "QA", "to": "In Progress"},
                                ],
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Workflow updated.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "states": [
                                            {"key": "BACKLOG", "name": "Backlog", "is_initial": True, "is_final": False},
                                            {"key": "IN_PROGRESS", "name": "In Progress", "is_initial": False, "is_final": False},
                                            {"key": "QA", "name": "QA", "is_initial": False, "is_final": False},
                                            {"key": "RELEASED", "name": "Released", "is_initial": False, "is_final": True},
                                        ],
                                        "transitions": [
                                            {"from": "BACKLOG", "to": "IN_PROGRESS"},
                                            {"from": "IN_PROGRESS", "to": "QA"},
                                            {"from": "QA", "to": "RELEASED"},
                                            {"from": "QA", "to": "IN_PROGRESS"},
                                        ],
                                    },
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            }
        },
        # ------------------------------------------------------------------ #
        # Sprints
        # ------------------------------------------------------------------ #
        "/api/v1/projects/{project_id}/sprints/": {
            "get": {
                "summary": "List project sprints",
                "operationId": "listSprints",
                "tags": ["Sprints"],
                "parameters": [
                    _PATH_PROJECT_ID,
                    *_PAGINATION_PARAMS,
                    {
                        "name": "status",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["planned", "active", "completed"]},
                        "description": "Filter sprints by status.",
                        "example": "active",
                    },
                    {
                        "name": "start_after",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Sprints starting on or after this date.",
                        "example": "2026-02-01",
                    },
                    {
                        "name": "end_before",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Sprints ending on or before this date.",
                        "example": "2026-03-31",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Paginated sprint list.",
                        "content": {
                            "application/json": {
                                "example": {
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
                                                "task_count": 8,
                                            }
                                        ],
                                        "count": 1,
                                        "page": 1,
                                        "page_size": 25,
                                        "next_page": None,
                                        "previous_page": None,
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "post": {
                "summary": "Create a sprint",
                "operationId": "createSprint",
                "tags": ["Sprints"],
                "description": "Creates a sprint in the project. Requires project-manager permission.",
                "parameters": [_PATH_PROJECT_ID],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name", "start_date", "end_date"],
                                "properties": {
                                    "name": {"type": "string", "example": "Sprint 2"},
                                    "goal": {"type": "string", "example": "Dashboard and notifications."},
                                    "start_date": {"type": "string", "format": "date", "example": "2026-02-15"},
                                    "end_date": {"type": "string", "format": "date", "example": "2026-02-28"},
                                    "status": {"type": "string", "enum": ["planned", "active", "completed"], "default": "planned"},
                                },
                            },
                            "example": {
                                "name": "Sprint 2",
                                "goal": "Dashboard and notifications.",
                                "start_date": "2026-02-15",
                                "end_date": "2026-02-28",
                            },
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Sprint created.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "id": 4,
                                        "name": "Sprint 2",
                                        "goal": "Dashboard and notifications.",
                                        "status": "planned",
                                        "start_date": "2026-02-15",
                                        "end_date": "2026-02-28",
                                    },
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        "/api/v1/projects/{project_id}/sprints/{sprint_id}/": {
            "get": {
                "summary": "Retrieve sprint detail",
                "operationId": "getSprint",
                "tags": ["Sprints"],
                "parameters": [
                    _PATH_PROJECT_ID,
                    {"name": "sprint_id", "in": "path", "required": True, "schema": {"type": "integer"}, "example": 3},
                ],
                "responses": {
                    "200": {"description": "Sprint detail.", "content": {"application/json": {"example": {"status": "success", "data": {"id": 3, "name": "Sprint 1", "goal": "Login flow.", "status": "active", "start_date": "2026-02-01", "end_date": "2026-02-14", "task_count": 8}}}}},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "patch": {
                "summary": "Update sprint",
                "operationId": "updateSprint",
                "tags": ["Sprints"],
                "parameters": [
                    _PATH_PROJECT_ID,
                    {"name": "sprint_id", "in": "path", "required": True, "schema": {"type": "integer"}, "example": 3},
                ],
                "requestBody": {"required": True, "content": {"application/json": {"example": {"status": "active", "goal": "Updated goal."}}}},
                "responses": {
                    "200": {"description": "Sprint updated.", "content": {"application/json": {"example": {"status": "success", "data": {"id": 3, "status": "active"}}}}},
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "delete": {
                "summary": "Delete sprint",
                "operationId": "deleteSprint",
                "tags": ["Sprints"],
                "description": "Deletes a sprint. Fails if the sprint has tasks assigned to it.",
                "parameters": [
                    _PATH_PROJECT_ID,
                    {"name": "sprint_id", "in": "path", "required": True, "schema": {"type": "integer"}, "example": 3},
                ],
                "responses": {
                    "200": {"description": "Sprint deleted.", "content": {"application/json": {"example": {"status": "success", "message": "Sprint deleted successfully.", "data": {"deleted_sprint_id": 3}}}}},
                    "400": {"description": "Sprint has tasks.", "content": {"application/json": {"example": {"status": "error", "message": "A sprint with assigned tasks cannot be deleted.", "errors": {}}}}},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        # ------------------------------------------------------------------ #
        # Milestones
        # ------------------------------------------------------------------ #
        "/api/v1/projects/{project_id}/milestones/": {
            "get": {
                "summary": "List project milestones",
                "operationId": "listMilestones",
                "tags": ["Milestones"],
                "parameters": [
                    _PATH_PROJECT_ID,
                    *_PAGINATION_PARAMS,
                    {
                        "name": "status",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["planned", "in_progress", "completed", "cancelled"]},
                        "description": "Filter milestones by status.",
                        "example": "planned",
                    },
                    {
                        "name": "target_after",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Milestones with target_date >= this value.",
                        "example": "2026-03-01",
                    },
                    {
                        "name": "target_before",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "format": "date"},
                        "description": "Milestones with target_date <= this value.",
                        "example": "2026-06-30",
                    },
                ],
                "responses": {
                    "200": {"description": "Paginated milestone list.", "content": {"application/json": {"example": {"status": "success", "data": {"milestones": [{"id": 1, "name": "Alpha Release", "description": "Internal alpha.", "target_date": "2026-03-01", "task_count": 12}], "count": 1, "page": 1, "page_size": 25, "next_page": None, "previous_page": None}}}}},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "post": {
                "summary": "Create a milestone",
                "operationId": "createMilestone",
                "tags": ["Milestones"],
                "description": "Creates a milestone. Requires project-manager permission.",
                "parameters": [_PATH_PROJECT_ID],
                "requestBody": {"required": True, "content": {"application/json": {"example": {"name": "Beta Release", "description": "Public beta.", "target_date": "2026-05-01"}}}},
                "responses": {
                    "201": {"description": "Milestone created.", "content": {"application/json": {"example": {"status": "success", "data": {"id": 2, "name": "Beta Release", "description": "Public beta.", "target_date": "2026-05-01", "status": "planned"}}}}},
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        # ------------------------------------------------------------------ #
        # Comments
        # ------------------------------------------------------------------ #
        "/api/v1/projects/{project_id}/tasks/{task_id}/comments/": {
            "get": {
                "summary": "List task comments",
                "operationId": "listComments",
                "tags": ["Comments"],
                "parameters": [_PATH_PROJECT_ID, _PATH_TASK_ID, *_PAGINATION_PARAMS],
                "responses": {
                    "200": {
                        "description": "Paginated comment list.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "comments": [
                                            {
                                                "id": 55,
                                                "task_id": 23,
                                                "author": {"id": 1, "name": "Alice Nguyen"},
                                                "content": "LGTM, merging.",
                                                "created_at": "2026-02-10T14:00:00+00:00",
                                            }
                                        ],
                                        "count": 1,
                                        "page": 1,
                                        "page_size": 25,
                                        "next_page": None,
                                        "previous_page": None,
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "post": {
                "summary": "Add a task comment",
                "operationId": "createComment",
                "tags": ["Comments"],
                "parameters": [_PATH_PROJECT_ID, _PATH_TASK_ID],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["content"],
                                "properties": {"content": {"type": "string", "example": "LGTM, merging."}},
                            },
                            "example": {"content": "LGTM, merging."},
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Comment created.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "message": "Comment created successfully.",
                                    "data": {
                                        "id": 55,
                                        "task_id": 23,
                                        "author": {"id": 1, "name": "Alice Nguyen"},
                                        "content": "LGTM, merging.",
                                        "created_at": "2026-02-10T14:00:00+00:00",
                                    },
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        "/api/v1/projects/{project_id}/tasks/{task_id}/comments/{comment_id}/": {
            "patch": {
                "summary": "Update a comment",
                "operationId": "updateComment",
                "tags": ["Comments"],
                "description": "Updates the content of an owned comment. Project managers can edit any comment.",
                "parameters": [
                    _PATH_PROJECT_ID,
                    _PATH_TASK_ID,
                    {"name": "comment_id", "in": "path", "required": True, "schema": {"type": "integer"}, "example": 55},
                ],
                "requestBody": {"required": True, "content": {"application/json": {"example": {"content": "Updated comment text."}}}},
                "responses": {
                    "200": {"description": "Comment updated.", "content": {"application/json": {"example": {"status": "success", "message": "Comment updated successfully.", "data": {"id": 55, "content": "Updated comment text."}}}}},
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
            "delete": {
                "summary": "Delete a comment",
                "operationId": "deleteComment",
                "tags": ["Comments"],
                "parameters": [
                    _PATH_PROJECT_ID,
                    _PATH_TASK_ID,
                    {"name": "comment_id", "in": "path", "required": True, "schema": {"type": "integer"}, "example": 55},
                ],
                "responses": {
                    "200": {"description": "Comment deleted.", "content": {"application/json": {"example": {"status": "success", "message": "Comment deleted successfully.", "data": {"deleted_comment_id": 55}}}}},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            },
        },
        # ------------------------------------------------------------------ #
        # Reports
        # ------------------------------------------------------------------ #
        "/api/v1/projects/{project_id}/reports/": {
            "get": {
                "summary": "Retrieve project progress, velocity, and workload reports",
                "operationId": "getReport",
                "tags": ["Reports"],
                "description": (
                    "Returns three structured report sections for the project:\n\n"
                    "- **progress** – overall task completion and effort metrics.\n"
                    "- **velocity** – per-sprint and average velocity data.\n"
                    "- **workload** – per-member task and effort breakdown."
                ),
                "parameters": [_PATH_PROJECT_ID],
                "responses": {
                    "200": {
                        "description": "Structured project report.",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "success",
                                    "data": {
                                        "project_id": 7,
                                        "progress": {
                                            "total_tasks": 20,
                                            "completed_tasks": 8,
                                            "in_progress_tasks": 5,
                                            "overdue_tasks": 2,
                                            "completion_percentage": "40.00",
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
                                                    "is_closed": True,
                                                }
                                            ],
                                            "closed_sprint_count": 1,
                                            "average_velocity": "72.00",
                                        },
                                        "workload": [
                                            {
                                                "name": "Bob Smith",
                                                "email": "bob@example.com",
                                                "total_tasks": 6,
                                                "active_tasks": 3,
                                                "completed_tasks": 3,
                                                "estimated_effort": "48.00",
                                                "actual_effort": "36.00",
                                            }
                                        ],
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "429": {"$ref": "#/components/responses/TooManyRequests"},
                },
            }
        },
    },
}


def openapi_spec_api(request):
    """Return the OpenAPI 3.0 specification as JSON."""
    return JsonResponse(OPENAPI_SPEC)


def api_docs_viewer(request):
    """Render a human-readable HTML view of the API documentation."""
    return render(request, "api_docs.html", {"spec": OPENAPI_SPEC})
