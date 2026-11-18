import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from api.docs import OPENAPI_SPEC


class ApiIntegrationDocsTests(TestCase):
    def test_openapi_spec_endpoint_returns_valid_spec(self):
        response = self.client.get(reverse("api:openapi-spec"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["openapi"], "3.0.3")
        self.assertIn("info", data)
        self.assertIn("paths", data)
        self.assertIn("components", data)

    def test_openapi_spec_contains_all_core_paths(self):
        paths = OPENAPI_SPEC["paths"]
        expected_paths = [
            "/api/v1/projects/",
            "/api/v1/projects/{project_id}/",
            "/api/v1/projects/{project_id}/tasks/",
            "/api/v1/tasks/{task_id}/",
            "/api/v1/tasks/{task_id}/status/",
            "/api/v1/projects/{project_id}/members/",
            "/api/v1/projects/{project_id}/members/{membership_id}/",
            "/api/v1/projects/{project_id}/workflow/",
            "/api/v1/projects/{project_id}/workflow/configure/",
            "/api/v1/projects/{project_id}/sprints/",
            "/api/v1/projects/{project_id}/sprints/{sprint_id}/",
            "/api/v1/projects/{project_id}/milestones/",
            "/api/v1/projects/{project_id}/tasks/{task_id}/comments/",
            "/api/v1/projects/{project_id}/tasks/{task_id}/comments/{comment_id}/",
            "/api/v1/projects/{project_id}/reports/",
        ]
        for path in expected_paths:
            self.assertIn(path, paths, f"Path {path} should be documented in OpenAPI spec")

    def test_openapi_spec_documents_security_and_components(self):
        components = OPENAPI_SPEC["components"]
        self.assertIn("securitySchemes", components)
        self.assertIn("bearerAuth", components["securitySchemes"])
        self.assertIn("sessionAuth", components["securitySchemes"])

        schemas = components.get("schemas", {})
        for schema_key in ["Error", "Success", "Project", "Task", "Membership", "Sprint", "Milestone", "Comment"]:
            self.assertIn(schema_key, schemas, f"Schema {schema_key} missing from components")

        responses = components.get("responses", {})
        for resp_key in ["Unauthorized", "Forbidden", "NotFound", "TooManyRequests"]:
            self.assertIn(resp_key, responses, f"Response {resp_key} missing from components")

    def test_openapi_spec_description_covers_integration_topics(self):
        description = OPENAPI_SPEC["info"]["description"]
        self.assertIn("Authentication", description)
        self.assertIn("Bearer token", description)
        self.assertIn("Rate Limiting", description)
        self.assertIn("Retry-After", description)
        self.assertIn("Pagination", description)
        self.assertIn("Error Responses", description)
        self.assertIn("REVIEW", description)
        self.assertIn("DONE", description)

    def test_api_docs_html_viewer(self):
        response = self.client.get(reverse("api:api-docs"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("REST API &amp; Integrations Reference", content)
        self.assertIn("/api/v1/projects/", content)
        self.assertIn("/api/v1/openapi.json", content)
        self.assertIn("Authentication", content)
        self.assertIn("Rate Limiting", content)

    def test_api_integration_examples_markdown_file_exists_and_covers_topics(self):
        docs_file = settings.PROJECT_ROOT / "docs" / "API_INTEGRATION_EXAMPLES.md"
        self.assertTrue(docs_file.exists(), "docs/API_INTEGRATION_EXAMPLES.md must exist")
        text = docs_file.read_text(encoding="utf-8")
        self.assertIn("## Authentication", text)
        self.assertIn("Bearer", text)
        self.assertIn("## Rate Limiting", text)
        self.assertIn("Retry-After", text)
        self.assertIn("## Pagination and Filtering", text)
        self.assertIn("## Error Response Format", text)
        self.assertIn("## Task Status and Workflow", text)
        self.assertIn("TODO → IN_PROGRESS → REVIEW → DONE", text)
        self.assertIn("## Project Memberships", text)
        self.assertIn("## Sprints", text)
        self.assertIn("## Milestones", text)
        self.assertIn("## Task Comments", text)
        self.assertIn("## Project Reports", text)
