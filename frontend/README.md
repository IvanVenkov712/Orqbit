# Orqbit frontend

The frontend is a React, TypeScript, and Vite application intended to become a small dashboard for submitting jobs, inspecting outcomes, and registering independent workers.

The current UI is still the Vite starter. Routing, authentication, job and worker screens, and the recommended visual design are planned.

## Guides

- [Frontend roadmap](docs/roadmap.md): implementation order, acceptance criteria, and deferred features.
- [Frontend development guide](docs/development.md): local setup, source organization, API integration, state, visual style, and verification.
- [Backend API reference](../docs/api.md): current requests, responses, authentication, and permissions.

## Local development

Start the backend on port 8000 using the [backend development guide](../docs/development.md#running-the-api-locally). Then, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite. Browser requests to `/api` are forwarded to the backend with that prefix removed. The [development guide](docs/development.md#running-the-frontend) also describes the existing Docker Compose arrangement.

From `frontend/`, run `npm run lint` for Oxlint and `npm run build` for TypeScript checking and the production build. No frontend test runner is configured yet.
