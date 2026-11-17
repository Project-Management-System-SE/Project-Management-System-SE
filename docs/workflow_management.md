# Configurable Project Workflows and Transition Enforcement

## Overview
The Workflow Management subsystem enforces state machine transitions for tasks within each project. By default, tasks must progress through standard lifecycle stages (`TODO -> IN_PROGRESS -> IN_REVIEW -> DONE`). Project Managers can customize and override these transition rules per project.

---

## Default Transition State Machine

```
   [ To Do ]
       |
       v
[ In Progress ] <-----> [ In Review ]
       |                      |
       |                      v
       +-----------------> [ Done ]
```

### Transition Matrix
- **To Do**: Permitted to transition to **In Progress**. Direct transitions to **Done** or **In Review** are blocked by default.
- **In Progress**: Permitted to transition to **In Review** or back to **To Do**.
- **In Review**: Permitted to transition to **Done** (approved) or back to **In Progress** (changes requested).
- **Done**: Can be reopened back to **In Progress**.

---

## Backend Enforcement Engine
1. `backend/projects/workflow.py`: Contains `get_allowed_transitions(project, current_status)` and `is_valid_transition(project, from_status, to_status)`.
2. Model: `ProjectWorkflowTransition` stores per-project custom overrides.
3. Views: `task_update_status` and `task_update` enforce transitions atomically on the server.
4. Security: Only users satisfying `can_manage_project(user, project)` can access `/projects/<id>/workflow/` and alter rules.
