# Orqbit frontend

React, TypeScript, and Vite interface for submitting jobs, inspecting outcomes, and registering independent workers.

See the [frontend roadmap](docs/roadmap.md) for remaining interface work.

## Guides

- [Frontend roadmap](docs/roadmap.md): implementation order, acceptance criteria, and deferred features.
- [Frontend development guide](docs/development.md): local setup, source organization, API integration, state, visual style, and verification.
- [Backend API reference](../docs/api.md): current requests, responses, authentication, and permissions.

## Local development

For the complete setup without Docker, follow the [local frontend guide](docs/development.md#without-docker-powershell), starting with its linked PostgreSQL and backend instructions. It also covers opening the interface, registration, and login.

Start the backend on port 8000 using the [backend development guide](../docs/development.md#running-the-api-locally). Then, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite. Browser requests to `/api` are forwarded to the backend with that prefix removed. The [development guide](docs/development.md#running-the-frontend) also describes the existing Docker Compose arrangement.

From `frontend/`, run `npm test` for Vitest, `npm run lint` for Oxlint, and `npm run build` for TypeScript checking and the production build.
