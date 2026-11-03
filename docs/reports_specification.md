# Downloadable Project Reports and Metrics Specification

## Overview
The Reporting Subsystem provides project members and managers with downloadable analytics in standard CSV formats. All metrics are calculated dynamically from actual saved database records and enforce project membership access boundaries.

---

## Report Types & Export Formats

### 1. Detailed Tasks Report (`?type=tasks`)
- **Format**: Comma-Separated Values (`text/csv`)
- **Columns**:
  - `Task ID`: Unique integer identifier.
  - `Project`: Project name.
  - `Title`: Task headline.
  - `Status`: Current workflow state (`TODO`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`).
  - `Priority`: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
  - `Assignee`: Assigned member name or `Unassigned`.
  - `Sprint`: Associated sprint or `Backlog`.
  - `Milestone`: Milestone identifier or `None`.
  - `Estimated Hours`: Planned effort in decimal hours.
  - `Actual Hours`: Logged effort in decimal hours.
  - `Due Date`: ISO 8601 target delivery date (`YYYY-MM-DD`).
  - `Created At` / `Updated At`: Timestamps in UTC.

### 2. Executive Summary Report (`?type=summary`)
- **Format**: Comma-Separated Values (`text/csv`)
- **Sections**:
  1. **Project Metadata**: Name, current status, owner, generation timestamp.
  2. **Progress KPIs**: Total tasks, completed tasks, completion rate (%), total estimated vs actual effort, effort variance, overdue task count.
  3. **Sprint Velocity**: Closed sprint count, average delivery velocity per sprint, breakdown per sprint.
  4. **Team Workload Allocation**: Assigned tasks, active tasks, completed tasks, estimated hours, and logged hours per team member.

---

## Security & Permission Boundaries
- Access to project reports and download endpoints requires active project membership or administrative privileges.
- Unauthenticated requests are redirected to login (`302`).
- Unauthorized requests from non-members receive HTTP 404/403 to prevent project enumeration.
