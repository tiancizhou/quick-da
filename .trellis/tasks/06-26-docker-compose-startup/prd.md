# Add Docker Compose Startup

## Requirement

Provide Docker Compose support so the project can be started from the repository root with one command.

## Scope

- Build the Vue frontend and serve its production assets from the FastAPI backend.
- Run the backend inside a container on port 8000.
- Run PostgreSQL through Docker Compose and persist database data in a Docker volume.
- Persist generated app files in a separate Docker volume.
- Keep runtime configuration controlled through environment variables.

## Acceptance Criteria

- `docker compose up --build` starts the application service.
- The application is available at `http://localhost:8000`.
- Backend startup waits for PostgreSQL health and runs database migrations before serving requests.
- No secrets are committed.
