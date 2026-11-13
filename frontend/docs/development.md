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

**3. Open the interface.** Use Vite's printed Local URL, usually `http://localhost:5173`, and choose Create an account. Register, then sign in with your username and password. Existing accounts can sign in directly. Use Jobs to submit and inspect work, Workers to register worker credentials, and Producers to manage producer credentials. Run independent applications to submit/execute work outside the browser. Reloading the page preserves login until the token expires or you sign out.

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
  ProducersPage.tsx         Producer search, registration, details, and management
  ListControls.tsx          Shared filtering, sorting, and current-page grouping
  Icon.tsx                  Application icons
  ParameterEditor.tsx       Nested JSON parameter editing
  index.css                 Global styles and design variables
  App.module.css            Shared application styles
  api/
    client.ts               Shared fetch, authentication, and error handling
  tests/                    Interface behavior tests and shared test utilities
```

Follow these files and patterns when adding behavior. Extract shared components or feature directories only when a concrete change benefits from them; do not create placeholder layers. Do not import backend Python models into browser code.

## Screens and navigation

The current layout has sidebar navigation for Jobs, Workers, and Producers, plus the signed-in user's identity and sign-out action. Jobs is the default authenticated destination. At narrow widths, CSS adapts the sidebar and collection layouts. Client routes below are distinct from backend endpoints.

The header breadcrumb links to the workspace (Jobs), the current section's list, and the parent record on nested screens such as attempt history and worker editing. The current page is marked separately, and the browser tab title follows it. Breadcrumbs wrap on narrow screens; worker editing also provides a direct link back to worker details.

| Client route | Screen and behavior |
| --- | --- |
| `/login` | Login form and registration link |
| `/register` | Account registration, followed by login |
| `/jobs` | Accessible jobs from all owners, status/lost-attempt views, filters, sorting, grouping, and pagination; defaults to Pending |
| `/jobs/new` | Type, JSON parameters, and access policy |
| `/jobs/:jobId` | Status and identifiers, parameters, result/error, attempt history |
| `/jobs/:jobId/attempts` | Dedicated attempt-history view |
| `/workers` | Accessible workers from all owners, type/owner/active/date filters, sorting, grouping, pagination, and registration |
| `/workers/new` | Worker registration and one-time API-key display |
| `/workers/:workerId` | Worker metadata, supported types, visibility policy, owner-only edit link and API-key reissue |
| `/workers/:workerId/edit` | Owner-only supported-type, visibility and permitted-user editing, plus API-key reissue |
| `/producers` | Your producers, partial/exact name or ID search, and page-size selection |
| `/producers/new` | Producer registration and one-time API-key display |
| `/producers/:producerId` | Producer metadata, key reissue, deactivation, and deletion when unreferenced |

Give pages one clear primary action. Use real links for navigation and buttons for actions. Put status and identifying information first on job details, followed by JSON panels and attempt history. Keep returned API keys in local state on their immediate registration/reissue screen.

Preserve filters and pagination through query parameters, validate them before API requests, and reset the offset when filters change. Lists and attempts return arrays with `limit`/`offset`, not total counts. Use Previous/Next controls; a full page may require one more request to discover the end. Do not infer global totals from a page of accessible records.

Jobs and Workers browse all accessible owners unless **Owner username** is supplied. Filters and sorting apply on the server before pagination; collapsible groups and their counts apply only to the fetched page. Removing a filter or clearing filters preserves unrelated URL state. Job list requests default to lifecycle sorting in the interface, while the API itself defaults to descending ID when no sort is supplied.

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
| Edit worker | `PUT /api/workers/{id}`, supported types, visibility policy and optional permitted-user IDs |
| Reissue worker key | `POST /api/workers/{id}/api-key` |
| Find permitted users | `GET /api/users?query=...&limit=10`, `GET /api/users/{id}` |
| Suggest job types | `GET /api/job-types`, accessible workers' types with optional `query` and `limit` |
| Register/list producers | `POST /api/producers`, `GET /api/producers` |
| Read producer | `GET /api/producers/{id}`, `GET /api/producers/by-name/{name}` |
| Reissue producer key | `POST /api/producers/{id}/api-key` |
| Deactivate/delete producer | `POST /api/producers/{id}/deactivate`, `DELETE /api/producers/{id}` |

Use `Authorization: Bearer <access_token>` for user-protected requests, including worker/producer registration management. Worker and producer `X-API-Key` credentials belong to their independent applications. The dashboard does not claim work, report worker outcomes, or use producer keys for background submission.

The shared client supports both form and JSON requests, checks HTTP status, and translates string `detail` errors and FastAPI field-validation arrays into useful messages. It handles bodyless 204 responses for deletion. Show network failures separately from invalid input. Missing and inaccessible records both return 404; do not reveal or infer which case applies. Current creation routes return 200.

Persist only the access token in local storage, keeping passwords and current-user details out of browser persistence. Page reloads preserve login: validate the saved token's expiry, then load `/users/me/` before opening protected screens. Remove the saved token on expiry, logout, or authentication rejection; preserve it on network/server failures and offer a restoration retry. There is no token-refresh endpoint or server-side logout operation. On session expiry, cancel user-specific requests and clear cached records. Keep caches isolated between users. Registration returns user metadata, so it does not itself establish a logged-in session.

### Submission and credentials

Validate that parameters parse as a JSON object; arrays, primitives, and null are invalid top-level inputs. Start with `PRIVATE` policy. Generate a submission key, for example using `crypto.randomUUID()`, once for the intended request. Retain its payload and key when retrying an uncertain response. A fresh submission or deliberately revised request needs a new key. Do not automatically retry a changed payload with the old key, or create a new key merely because the response was lost.

Worker registration requires a name, nonempty supported types, and visibility policy. Producer registration requires a name. Show the returned `secret_api_key` only in the immediate creation/reissue result, with a copy action and instructions to save it. Avoid storing it in browser persistence, URLs, logs, or the long-lived query cache. Later reads cannot retrieve it. Both worker and producer screens expose owner-authorized key reissue with explicit confirmation that the old key stops working immediately. Worker reissue is available on both details and editing screens; leaving the screen, changing worker or reloading discards the displayed key. A lost response may mean the key changed; no automatic retry is performed.

Worker registration and editing use the same tag input for supported types. Add a type with Enter or Add, remove it with its × button, or remove the last tag with Backspace when the input is empty. The input suggests types from accessible workers and also accepts new types. Duplicates are removed; case and spaces are preserved because job types match exactly. Saving includes any text still in the input. At least one non-blank type of at most 100 characters is required. Both forms always display the **Permitted users** picker. Under `PRIVATE` or `ALL`, it is disabled with an explanation and a **Choose permitted users** button that selects `PERMITTED_USERS` and enables editing. Switching policies preserves selected tags and unfinished input. Search by username; suggestions show usernames and full names. Click a suggestion or use arrow keys and Enter to select a person. Selected usernames appear as removable tags and are excluded from suggestions. The picker accepts only selected directory users; typing numbers never adds users by ID. Unselected search text must be selected or cleared before saving. IDs remain internal to the API payload. Existing unavailable users retain a removable **Unavailable user** tag. Empty and failed searches have visible feedback, with a manual retry for failures. On editing, saving an empty selection clears all grants; other policies omit the field and preserve stored grants. The update endpoint also preserves grants when the field is omitted or null. Worker names cannot be changed by that endpoint. Cancel discards the draft; a successful save returns to refreshed details and invalidates worker lists.

Producer deactivation preserves jobs and disables producer-key authentication. Reissue does not reactivate credentials. Deletion of a producer referenced by jobs returns 409. The interface provides no producer reactivation action because the API has no corresponding endpoint.

Job forms show only the user/worker ID inputs relevant to the selected policy. Worker forms keep the permitted-user input visible and explain how to enable it. Explain the effect of grants: a worker claim grant does not automatically grant its owner user-facing job access. Worker visibility and job permissions are distinct. Use the API's user-discovery endpoints if adding searchable grant pickers. Consult the API reference for policy values and validation rules.

### Server state and polling

Use query keys that include the authenticated identity, resource ID, and applicable filters/pagination. Invalidate affected lists after successful creation and use the server's response to navigate to the created resource. Keep form drafts separate from fetched records.

Poll visible pending/running job details every few seconds, with three seconds as an initial choice. Stop the interval after `SUCCEEDED` or `FAILED`, when the screen is left, or when the session ends. Refresh attempt history with job updates, including the final transition. Pause interval polling while the tab is hidden and refresh stale data when it becomes visible again.

Configure query freshness, interval polling, and retries deliberately. Avoid retrying authentication, permission, validation, and not-found responses automatically. Disable automatic mutation retries initially; a user-triggered submission retry must retain its original key and payload. Keep the last successful data visible during background refresh and show a quiet refresh error when needed.

## Visual design

The implemented dashboard uses light surfaces, dark text, teal actions, compact tables, and the supplied Orqbit icon for branding and the favicon. Continue the existing sidebar, collection toolbar, status tabs, cards, and responsive layouts when adding screens. Dark mode is deferred.

### Palette and typography

CSS custom properties in `index.css` define the global palette, fonts, and spacing; `App.module.css` contains shared scoped application styles. Reuse those values and patterns. A CSS framework or large component library is not required.

| Token | Value | Use |
| --- | --- | --- |
| `--color-background` | `#F7F9FB` | Page background |
| `--color-surface` | `#FFFFFF` | Panels and inputs |
| `--color-text` | `#202B3C` | Primary text |
| `--color-text-secondary` | `#647185` | Supporting text |
| `--color-divider` | `#E4E9EF` | Subtle content separators |
| `--color-primary` | `#087E78` | Main actions |
| `--color-input-border` | `#9AA7B6` | Control boundaries |

The existing font stacks start with Segoe UI for normal text and Cascadia Code for monospace. The root font is 14px/1.55; component headings and table sizes are defined in the stylesheets. Spacing tokens use 4, 8, 12, 16, 24, and 32px, and the shared radius token is 10px. Treat the stylesheets as the source of truth for exact values.

### Components and interaction

- Tables use clear column headings, horizontal separators, subtle row hover, and explicit detail links. Preserve readable columns at narrow widths with contained scrolling where necessary.
- Forms use labels above controls, concise help text, inline validation errors, and a visible submitting state. `ParameterEditor.tsx` builds nested JSON objects/lists from typed inputs; a separate code editor is not required.
- Primary buttons use solid teal with contrasting text. Secondary actions use outlined or plain treatments. Keep destructive styling reserved for actual destructive operations when supported.
- JSON panels use a pale background, preserved indentation, monospace text, and wrapping for long content. They currently render selectable text, without a dedicated copy button. Render JSON as text rather than injecting HTML.
- Status badges include text: slate for `PENDING`, blue for `RUNNING`, green for `SUCCEEDED`, and red for `FAILED`. Label `LOST` as an expired attempt lease, without treating it as proof that the worker process stopped.
- Use visible keyboard focus, associated form labels, semantic tables, and accessible copy/error feedback. Color must be accompanied by text or another cue.
- Keep hover transitions brief and honor reduced-motion preferences. Background polling should not flash the page, move focus, or repeatedly announce unchanged content.

Check actual color combinations against WCAG: normal text needs 4.5:1 contrast and large text needs 3:1. Subtle divider colors are for grouping; input boundaries and focus indicators need sufficient visibility. See [text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and [use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html).

## Backend limits that affect the interface

- Job reads expose IDs, type, params, status, result/error, attempt IDs, timestamps, retry counters, and `available_at`. They omit permission policies and grant lists. Do not invent job durations or permission details.
- Attempt history includes worker attribution and creation/update timestamps. `updated_at` is not a dedicated finished timestamp. Display timezone information clearly when formatting timestamps.
- Worker `active` indicates authentication eligibility, not online status. Attempt heartbeats do not provide a separate worker-process liveness signal.
- Recovery schedules retries for lost attempts while budget remains. A worker-reported failure is terminal. Use [recovery and bounded retries](../../docs/api.md#recovery-and-bounded-retries) when presenting these states.
- Worker supported-type, visibility and permitted-user updates, plus API-key reissue, have owner-only browser controls. Worker deletion is an implemented API operation but currently lacks a browser control. Producer management includes key reissue, deactivation, and safe deletion in both API and UI.
- Job update/delete, cancellation, manual replay, account management, token refresh, worker deactivation, and producer reactivation have no current endpoints. Add their controls only when backend contracts exist.
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
