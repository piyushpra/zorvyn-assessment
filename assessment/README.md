# Finance Data Processing and Access Control Backend

This repository contains a backend assessment project for a finance dashboard system. It focuses on data modeling, API design, business rules, validation, and role-based access control.

## Best Files To Review First

- `finance_backend/app.py`
  - Route registration, auth checks, and request validation flow
- `finance_backend/services/users.py`
  - User management, login, and admin-only business rules
- `finance_backend/services/records.py`
  - Financial record CRUD, filtering, pagination, and soft delete
- `finance_backend/services/dashboard.py`
  - Summary totals and trend aggregation logic
- `tests/test_api.py`
  - End-to-end API behavior checks for roles and core flows

## What This Implements

- User management with role assignment and active/inactive status
- Token-based authentication with seeded demo users
- Role-based access control for viewers, analysts, and admins
- Financial record CRUD with filtering, pagination, and soft delete
- Dashboard summary APIs for totals, category breakdowns, recent activity, and trends
- SQLite persistence with automatic schema creation and seed data
- Input validation and structured JSON error responses
- A small unit/integration-style test suite using Python's standard library

## Tech Choices

- Language: Python 3.9+
- Persistence: SQLite via the standard library `sqlite3`
- Validation: `pydantic`
- HTTP layer: a lightweight WSGI app built with the Python standard library

I intentionally kept the project dependency-light so it can run in constrained environments without needing a full framework install, while still preserving a clean service-oriented structure.

## Project Structure

```text
finance_backend/
  app.py          # Application wiring and route registration
  config.py       # Environment-driven settings
  db.py           # Schema creation and demo seeding
  errors.py       # Structured application errors
  http.py         # Tiny router, request parsing, JSON responses
  schemas.py      # Pydantic request/query validation models
  security.py     # Password hashing and bearer token helpers
  server.py       # WSGI server bootstrap
  services/
    users.py      # User and authentication business rules
    records.py    # Financial record CRUD and filtering
    dashboard.py  # Dashboard aggregations
    common.py     # Shared money/serialization helpers
tests/
  test_api.py     # API behavior tests
```

## Roles and Access Rules

- `viewer`
  - Can access dashboard summary and trend endpoints
  - Cannot view raw financial records
  - Cannot create, update, or delete records
- `analyst`
  - Can read financial records
  - Can access dashboard summary and trend endpoints
  - Cannot mutate records or manage users
- `admin`
  - Full access to users, records, and dashboard endpoints
  - Can create/update/deactivate users
  - Can create/update/delete records

Additional business rules:

- Inactive users cannot authenticate
- Admins cannot deactivate or delete themselves
- The last active admin cannot be demoted or deactivated
- Record deletion is implemented as soft delete

## Running the Project

1. Install the dependency:

```bash
python3 -m pip install -r requirements.txt
```

2. Start the API:

```bash
python3 -m finance_backend
```

3. The service will be available at:

```text
http://127.0.0.1:8000
```

### Optional Environment Variables

- `FINANCE_DB_PATH`
  - Defaults to `./finance.db`
- `FINANCE_HOST`
  - Defaults to `127.0.0.1`
- `FINANCE_PORT`
  - Defaults to `8000`
- `FINANCE_DEBUG`
  - Defaults to `false`
- `FINANCE_SEED_DEMO_DATA`
  - Defaults to `true`

## Seeded Demo Users

When the database is empty and demo seeding is enabled, these users are created automatically:

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@finance.local` | `AdminPass123!` |
| Analyst | `analyst@finance.local` | `AnalystPass123!` |
| Viewer | `viewer@finance.local` | `ViewerPass123!` |

The seed also inserts a handful of demo financial records so the dashboard endpoints have useful data immediately.

## API Overview

### Auth

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

### Users

- `GET /api/v1/users`
- `POST /api/v1/users`
- `GET /api/v1/users/{user_id}`
- `PATCH /api/v1/users/{user_id}`
- `DELETE /api/v1/users/{user_id}`

`DELETE /api/v1/users/{user_id}` performs a deactivation rather than removing historical data references.

### Financial Records

- `GET /api/v1/records`
- `POST /api/v1/records`
- `GET /api/v1/records/{record_id}`
- `PATCH /api/v1/records/{record_id}`
- `DELETE /api/v1/records/{record_id}`

Supported record list filters:

- `type`
- `category`
- `start_date`
- `end_date`
- `q`
- `limit`
- `offset`

### Dashboard

- `GET /api/v1/dashboard/summary`
- `GET /api/v1/dashboard/trends`

Summary supports:

- total income
- total expenses
- net balance
- category-wise totals
- recent activity

Trend supports:

- `granularity=monthly|weekly`
- `periods=<1-24>`
- optional `end_date`
- optional `category`

## Example Requests

### Login

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@finance.local",
    "password": "AdminPass123!"
  }'
```

### Create a Record as Admin

```bash
curl -X POST http://127.0.0.1:8000/api/v1/records \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "499.99",
    "type": "expense",
    "category": "Software",
    "date": "2026-04-05",
    "notes": "Annual subscription"
  }'
```

### List Records with Filters

```bash
curl "http://127.0.0.1:8000/api/v1/records?type=expense&start_date=2026-04-01&limit=10" \
  -H "Authorization: Bearer <TOKEN>"
```

### Get Dashboard Summary

```bash
curl http://127.0.0.1:8000/api/v1/dashboard/summary \
  -H "Authorization: Bearer <TOKEN>"
```

### Get Monthly Trends

```bash
curl "http://127.0.0.1:8000/api/v1/dashboard/trends?granularity=monthly&periods=6" \
  -H "Authorization: Bearer <TOKEN>"
```

## Response Shape

Successful responses use:

```json
{
  "data": {}
}
```

Errors use:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": []
  }
}
```

## Running Tests

```bash
PYTHONPYCACHEPREFIX="$PWD/.pycache" python3 -m unittest discover -s tests -v
```

The `PYTHONPYCACHEPREFIX` setting keeps bytecode generation inside the project directory, which is useful in sandboxed environments.

## Assumptions and Tradeoffs

- Authentication is intentionally lightweight and token-based for assessment simplicity.
- There is no separate refresh token flow or password reset flow.
- User deletion is modeled as deactivation to preserve record ownership history.
- Money is stored as integer cents in SQLite to avoid floating point precision issues.
- A small custom HTTP layer is used instead of a framework to keep the project runnable with minimal setup.
