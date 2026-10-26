# Task Permission Matrix and Server-Side Validation Specification

## Overview
This specification details the role-based and project-level authorization rules governing task creation, retrieval, modification, reassignment, status workflow transitions, and deletion in the Project Management System.

### Role Hierarchy & Definitions
1. **System Administrator (Superuser / Staff)**:
   - Global authorization across all projects and tasks.
2. **Project Owner**:
   - Creator of the project. Possesses full managerial authority over project metadata, membership, sprints, milestones, and tasks.
3. **Project Manager (PM)**:
   - User assigned the `PROJECT_MANAGER` role via `ProjectMembership`. Has identical task administration rights to the Project Owner.
4. **Team Member**:
   - User assigned the `TEAM_MEMBER` role via `ProjectMembership`.
   - Authorized to view all tasks in the project.
   - Authorized to edit tasks where they are either the designated `assignee` or `created_by`.
   - Cannot reassign tasks to other team members without managerial privileges.
   - Cannot delete tasks.
5. **Non-Member / Anonymous User**:
   - Denied all access (HTTP 401 Unauthorized or HTTP 403 / 404 Forbidden).

---

## Permission Matrix

| Operation | Admin / Owner | Project Manager | Assigned Member | Creator Member | Other Member | Non-Member |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **View Task List** | Allowed | Allowed | Allowed | Allowed | Allowed | Denied (403/404) |
| **View Task Details** | Allowed | Allowed | Allowed | Allowed | Allowed | Denied (403/404) |
| **Create Task** | Allowed | Allowed | Denied (by default) | Denied | Denied | Denied (403) |
| **Edit Task Content** | Allowed | Allowed | Allowed | Allowed | Denied | Denied (403) |
| **Update Task Status** | Allowed | Allowed | Allowed | Allowed | Denied | Denied (403) |
| **Reassign Task** | Allowed | Allowed | Denied | Denied | Denied | Denied (403) |
| **Delete Task** | Allowed | Allowed | Denied | Denied | Denied | Denied (403) |

---

## Server-Side Validation Rules
1. **Title Validation**:
   - Must be between 3 and 200 characters long.
   - Cannot consist solely of whitespace.
   - HTML and script tags are disallowed/escaped to prevent Cross-Site Scripting (XSS).
2. **Assignee Validation**:
   - Assignee must possess active membership in the task's project or be the project owner. Cross-project assignment attempts are rejected on the server.
3. **Due Date Bounds**:
   - Task `due_date` cannot be earlier than the parent project's `start_date` (if defined).
4. **Status Workflow Transitions**:
   - Status updates must follow the valid workflow state machine. Arbitrary transitions are rejected on the backend.
