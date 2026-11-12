# Frontend development guide

Use this guide for setup and frontend working conventions. Track remaining interface tasks in the [roadmap](roadmap.md).

## Running the frontend

Use Node.js 22.12 or newer in the Node 22 release line and npm; the existing frontend Docker build uses Node 22. Install frontend dependencies independently of the backend and workers.

### Without Docker (PowerShell)

**1. Start the backend.** Follow [Running the API locally](../../docs/development.md#running-the-api-locally) for Python/uv prerequisites, PostgreSQL database creation, `backend/.env`, migrations, and API startup on port 8000. Keep the API terminal running and confirm the readiness check succeeds before attempting login.

**2. Start the frontend.** With Node.js/npm installed as described above, open a second PowerShell terminal at the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

**3. Open the interface.** Use Vite's printed Local URL, usually `http://localhost:5173`, and choose Create an account. Register, then sign in with your username and password. Existing accounts can sign in directly. Use Jobs to submit and inspect work and Workers to register worker credentials. Run an independent worker to execute submitted jobs. Reloading the page preserves login until the token expires or you sign out.

Keep both terminals running while using the application. Press `Ctrl+C` in each to stop its development server; your PostgreSQL database retains accounts and jobs.

`vite.config.ts` forwards `/api/...` to `http://localhost:8000/...`, removing `/api`. If the backend port changes, the development proxy must match it. Use relative `/api` URLs in browser code.

### With Docker Compose

For the existing container arrangement, first configure `.env.compose` using the [quickstart](../../docs/quickstart.md), then run from the repository root:

```powershell
docker compose --env-file .env.compose up --build --wait --wait-timeout 120 frontend recovery
```

Open `http://localhost:8080`. Nginx serves the built application, forwards `/api/` to `api:8000`, and falls back to `index.html` for client routes. Use Vite for frontend hot reload.

## Architecture and source organization

Keep `frontend/` alongside `backend/`. The browser communicates exclusively through Orqbit's public HTTP API. FastAPI owns validation, authorization, and job lifecycle transitions; independent workers claim and execute jobs outside the browser and API process.

Use React Router for navigation, TanStack Query for server records, local React state for forms and temporary UI state, and the authentication context for sessions. Filters and pagination belong in the URL. This scope does not need a separate global state library or server-rendering framework.

Source locations:

```text
src/
  main.tsx                  React entry point
  App.tsx                   Providers, routing, authentication and submission forms
  auth.tsx                  Authentication context and session restoration
  JobsPage.tsx              Job browsing
  JobDetailsPage.tsx        Job details and attempt history
  WorkersPage.tsx           Worker browsing, registration, and details
  ParameterEditor.tsx       Nested JSON parameter editing
  index.css                 Global styles and design variables
  App.module.css            Shared application styles
  api/
    client.ts               Shared fetch, authentication, and error handling
  tests/                    Interface behavior tests and shared test utilities
```

Follow these files and patterns when adding behavior. Extract shared components or feature directories only when a concrete change benefits from them; do not create placeholder layers. Do not import backend Python models into browser code.

## Screens and navigation

Use a simple top navigation bar with Jobs, Workers, and the current-user menu. Jobs is the default authenticated destination. Client routes below are distinct from backend endpoints.

| Client route | Screen and behavior |
| --- | --- |
| `/login` | Login form and registration link |
| `/register` | Account registration, followed by login |
| `/jobs` | Your jobs, status views, pagination, Submit job action |
| `/jobs/new` | Type, JSON parameters, and access policy |
| `/jobs/:jobId` | Status and identifiers, parameters, result/error, attempt history |
| `/jobs/:jobId/attempts` | Dedicated attempt-history view |
| `/workers` | Your workers, type filter, pagination, registration action |
| `/workers/new` | Worker registration and one-time API-key display |
| `/workers/:workerId` | Worker metadata, supported types, and visibility policy |

Give pages one clear primary action. Use real links for navigation and buttons for actions. Put status and identifying information first on job details, followed by JSON panels and attempt history. Keep worker registration and its one-time API-key display on the registration route.

Preserve filters and pagination through query parameters, validate them before API requests, and reset the offset when filters change. Lists and attempts return arrays with `limit`/`offset`, not total counts. Use Previous/Next controls; a full page may require one more request to discover the end. Do not infer global totals from a page of accessible records.

## API integration and session behavior

Use the current unversioned contract in the [API reference](../../docs/api.md); its proposed `/v1` endpoints are not implemented. Preserve endpoint slash conventions when constructing requests.

| Operation | Browser request through the proxy |
| --- | --- |
| Login | `POST /api/auth/login`, form-encoded `username` and `password` |
| Register | `POST /api/auth/register`, JSON account fields |
| Current user | `GET /api/users/me/` |
| Submit job | `POST /api/jobs/`, JSON and `Idempotency-Key` header |
| List/read jobs | `GET /api/jobs`, `GET /api/jobs/{id}` |
| Read attempts | `GET /api/jobs/{id}/attempts` |
| Register/list workers | `POST /api/workers`, `GET /api/workers` |
| Read worker | `GET /api/workers/{id}` |

Use `Authorization: Bearer <access_token>` for user-protected requests. Worker `X-API-Key` credentials belong to the independent worker. The dashboard registers and inspects workers; it does not claim work or report their outcomes.

The shared client should support both form and JSON requests, check HTTP status, and translate string `detail` errors and FastAPI field-validation arrays into useful messages. Show network failures separately from invalid input. Missing and inaccessible records both return 404; do not reveal or infer which case applies. Current creation routes return 200.

Persist only the access token in local storage, keeping passwords and current-user details out of browser persistence. Page reloads preserve login: validate the saved token's expiry, then load `/users/me/` before opening protected screens. Remove the saved token on expiry, logout, or authentication rejection; preserve it on network/server failures and offer a restoration retry. There is no token-refresh endpoint or server-side logout operation. On session expiry, cancel user-specific requests and clear cached records. Keep caches isolated between users. Registration returns user metadata, so it does not itself establish a logged-in session.

### Submission and credentials

Validate that parameters parse as a JSON object; arrays, primitives, and null are invalid top-level inputs. Start with `PRIVATE` policy. Generate a submission key, for example using `crypto.randomUUID()`, once for the intended request. Retain its payload and key when retrying an uncertain response. A fresh submission or deliberately revised request needs a new key. Do not automatically retry a changed payload with the old key, or create a new key merely because the response was lost.

Worker registration requires a name, nonempty supported types, and visibility policy. Show the returned `secret_api_key` only in the immediate creation result, with a copy action and instructions to save it. Avoid storing it in browser persistence, URLs, logs, or the long-lived query cache. Later reads cannot retrieve it, and the current API cannot rotate it.

Show only the user/worker ID inputs relevant to the selected policy and explain their effect. A worker claim grant does not automatically grant its owner user-facing job access. Worker visibility and job permissions are distinct. Use the API's user-discovery endpoints if adding searchable grant pickers. Consult the API reference for policy values and validation rules.

### Server state and polling

Use query keys that include the authenticated identity, resource ID, and applicable filters/pagination. Invalidate affected lists after successful creation and use the server's response to navigate to the created resource. Keep form drafts separate from fetched records.

Poll visible pending/running job details every few seconds, with three seconds as an initial choice. Stop the interval after `SUCCEEDED` or `FAILED`, when the screen is left, or when the session ends. Refresh attempt history with job updates, including the final transition. Pause interval polling while the tab is hidden and refresh stale data when it becomes visible again.

Configure query freshness, interval polling, and retries deliberately. Avoid retrying authentication, permission, validation, and not-found responses automatically. Disable automatic mutation retries initially; a user-triggered submission retry must retain its original key and payload. Keep the last successful data visible during background refresh and show a quiet refresh error when needed.

## Visual design

Use a calm, technical dashboard with light surfaces, navy text, teal actions, compact tables, and restrained decoration. Use the supplied Orqbit icon for application branding and the favicon. The palette follows its navy and aqua colors, with darker teal for readable controls. A dark developer-console theme or a denser industrial style could be considered later; begin with the light operational style.

### Palette and typography

Define CSS custom properties in `index.css`, then use CSS Modules beside components for scoped styles. Plain global CSS should cover base elements and tokens. A CSS framework or large component library is optional future work, not a prerequisite.

| Token | Value | Use |
| --- | --- | --- |
| `--color-background` | `#F5F8FC` | Page background |
| `--color-surface` | `#FFFFFF` | Panels and inputs |
| `--color-text` | `#101A35` | Primary text |
| `--color-text-secondary` | `#4C5C75` | Supporting text |
| `--color-divider` | `#DCE5EF` | Subtle content separators |
| `--color-primary` | `#0F6F78` | Main actions and focus indication |
| `--color-input-border` | `#64758B` | Visible control boundaries |

Use a system sans-serif stack for normal text and a system monospace stack for job types, IDs, and JSON. Start with 16px body text, 14px table text, and 24-28px page headings. Use spacing steps of 4, 8, 12, 16, 24, and 32px, and modest 6-8px corner radii. Centralize these values as variables rather than repeating arbitrary values.

### Components and interaction

- Tables use clear column headings, horizontal separators, subtle row hover, and explicit detail links. Preserve readable columns at narrow widths with contained scrolling where necessary.
- Forms use labels above controls, concise help text, inline validation errors, and a visible submitting state. Start JSON entry with a normal textarea; a code editor is not required.
- Primary buttons use solid teal with contrasting text. Secondary actions use outlined or plain treatments. Keep destructive styling reserved for actual destructive operations when supported.
- JSON panels use a pale background, preserved indentation, monospace text, scrolling for large content, and a copy action with feedback. Render JSON as text rather than injecting HTML.
- Status badges include text: slate for `PENDING`, blue for `RUNNING`, green for `SUCCEEDED`, and red for `FAILED`. Label `LOST` as an expired attempt lease, without treating it as proof that the worker process stopped.
- Use visible keyboard focus, associated form labels, semantic tables, and accessible copy/error feedback. Color must be accompanied by text or another cue.
- Keep hover transitions brief and honor reduced-motion preferences. Background polling should not flash the page, move focus, or repeatedly announce unchanged content.

Check actual color combinations against WCAG: normal text needs 4.5:1 contrast and large text needs 3:1. Subtle divider colors are for grouping; input boundaries and focus indicators need sufficient visibility. See [text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and [use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html).

## Backend limits that affect the interface

- Job reads expose IDs, type, params, status, result/error, attempt IDs, timestamps, retry counters, and `available_at`. They omit permission policies and grant lists. Do not invent job durations or permission details.
- Attempt history includes worker attribution and creation/update timestamps. `updated_at` is not a dedicated finished timestamp. Display timezone information clearly when formatting timestamps.
- Worker `active` indicates authentication eligibility, not online status. Attempt heartbeats do not provide a separate worker-process liveness signal.
- Recovery schedules retries for lost attempts while budget remains. A worker-reported failure is terminal. Use [recovery and bounded retries](../../docs/api.md#recovery-and-bounded-retries) when presenting these states.
- There are no update/delete, cancellation, account-management, token-refresh, or key-rotation endpoints. Add their controls only when backend contracts exist.
- Client route guards improve navigation; authorization remains enforced by the API.

## Verification and working practices

From `frontend/`:

```powershell
npm test
npm run lint
npm run build
```

These scripts run Vitest, Oxlint, and TypeScript/Vite respectively. Reuse the Vitest/Testing Library setup and prioritize observable behavior such as invalid JSON, authentication errors, submission-key reuse after a lost response, URL filters, one-time secret display, and terminal-state polling. Use controlled responses and timers rather than arbitrary sleeps.

Verify the first complete flow against the real backend and independent example worker. Check direct route loading, keyboard use, narrow layouts, empty lists, unavailable records, API failures, and expired credentials. Mocked frontend responses do not establish backend permissions or concurrency guarantees; the existing backend tests cover those concerns.

Before editing, state the expected files and their purpose. Keep changes cohesive and update one relevant documentation location when behavior changes. Run configured checks and report what actually ran, including limitations. Do not change backend contracts, dependencies, infrastructure, or CI merely to complete surrounding roadmap work.

## References

- [React's guidance for building an application from scratch](https://react.dev/learn/build-a-react-app-from-scratch) describes the routing and data-fetching choices relevant to the existing Vite setup.
- [TanStack Query defaults](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults) explains freshness and automatic refetch/retry behavior to configure when introducing queries.
- The [frontend roadmap](roadmap.md) defines implementation order; the [backend API reference](../../docs/api.md) defines supported behavior.
