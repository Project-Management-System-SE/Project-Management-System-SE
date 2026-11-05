# Production Database Configuration Guide

## Overview
The application supports multi-dialect database configuration via standard environment variables. By default, SQLite is utilized for zero-configuration local development. For production deployments, PostgreSQL or MySQL can be targeted without modifying application source code.

---

## Environment Variables Reference

| Variable | Description | Default (Local Dev) | Production Example |
| :--- | :--- | :--- | :--- |
| `DJANGO_DB_ENGINE` | Database dialect (`sqlite3`, `postgresql`, `mysql`) | `sqlite3` | `postgresql` |
| `DJANGO_DB_NAME` | Database schema or file path | `db.sqlite3` | `project_management_prod` |
| `DJANGO_DB_USER` | Database user account | `""` | `pms_admin` |
| `DJANGO_DB_PASSWORD` | Secure authentication password | `""` | `[SECURE_PASSWORD]` |
| `DJANGO_DB_HOST` | Database host or socket | `localhost` | `db.production.internal` |
| `DJANGO_DB_PORT` | Port number | `""` | `5432` |
| `DJANGO_DB_CONN_MAX_AGE` | Connection pooling duration in seconds | `600` | `600` |

---

## Docker Compose Setup Example (PostgreSQL)

```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_DB: project_management_prod
      POSTGRES_USER: pms_admin
      POSTGRES_PASSWORD: supersecretpassword
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  web:
    build: .
    command: python backend/manage.py runserver 0.0.0.0:8000
    environment:
      DJANGO_DB_ENGINE: postgresql
      DJANGO_DB_NAME: project_management_prod
      DJANGO_DB_USER: pms_admin
      DJANGO_DB_PASSWORD: supersecretpassword
      DJANGO_DB_HOST: db
      DJANGO_DB_PORT: 5432
    depends_on:
      - db

volumes:
  pgdata:
```

---

## Verifying Database Health
Run the diagnostic command to verify connectivity, latency, and applied migrations:
```bash
python backend/manage.py check_db_connection
```
