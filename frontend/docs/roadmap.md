# Frontend roadmap

Build a small operational dashboard around Orqbit's existing public HTTP API. Prioritize a complete submission-and-result flow, then add browsing and management screens. The [development guide](development.md) records the proposed architecture and visual design; the [API reference](../../docs/api.md) records the implemented backend contract.

## Current state

The frontend contains a React/TypeScript application shell with React Router, a light responsive layout, Jobs/Workers navigation, login and registration forms, a current-user area with logout, and protected application routes with explicitly labeled feature placeholders. Vite and Nginx proxy `/api` to the backend. Docker Compose includes a frontend service on port 8080.

Steps 1–3 are implemented; steps 4–9 remain planned. Vitest, jsdom, and React Testing Library provide focused tests through `npm test`. Shared HTTP transport and persistent token authentication are available; job/worker API integration, feature screens, and TanStack Query are not implemented yet.

Treat each milestone as a separate change, splitting it further when necessary. Prefer changes to one to three files; explain additional files when directly necessary. Add dependencies only when their behavior is introduced. Each behavior change should include focused verification, rather than postponing testing until the final milestone.

## 1. Application shell and visual foundation — completed

Replace the starter content with a simple layout. Introduce React Router, navigation for Jobs and Workers, a current-user area, and route placeholders. Establish the light palette, typography, spacing, controls, and focus styles from the development guide.

**Done when:** navigation and browser back/forward work, unknown routes have a useful response, and the layout works at narrow widths. Keep placeholders clearly identified until their screens exist.

**Implemented:** `/` redirects to `/jobs`. The Jobs, submission, job details, Workers, worker details, login, and registration routes render labeled placeholders. Navigation highlights the current section, including detail routes. Unknown routes offer a link back to Jobs. Shared styles establish the guide's light palette, typography, spacing, controls, keyboard focus, and skip link. The current-user area explicitly shows “Not signed in” until authentication is implemented.

**Verification:** `npm test` passed all 11 routing/component tests, including browser history, direct route entry, active navigation, placeholder links, and unknown-route recovery. `npm run lint` and `npm run build` passed. Headless Edge checks confirmed navigation, browser back/forward, direct reload, unknown-route recovery, visible keyboard focus on the skip link, and no horizontal overflow at 320px, 390px, and 1280px. Direct route requests to the Vite server returned the application shell. No backend integration is introduced in this step.

## 2. Shared HTTP client — completed

Add `src/api/client.ts` for `/api` requests, bearer authentication, response parsing, and meaningful errors. Support JSON and form-encoded bodies. Define request/response types beside each feature when needed; keep transport concerns out of page components.

**Done when:** the client handles success, network failures, string API errors, and field-validation errors. Login can send form data without an incorrect JSON content type. Credentials and raw internal errors are not exposed in diagnostics or the UI.

**Implemented:** `src/api/client.ts` exports `apiRequest<T>(path, options)` and `ApiError`. Paths such as `/users/me/` are prefixed with `/api` without changing endpoint slashes or query parameters. Options accept a per-request `token`, `json` or a form-encoded `URLSearchParams` in `form`, plus standard fetch options and headers. The client sets the matching content type, preserves custom headers such as `Idempotency-Key`, parses JSON, and returns `undefined` for empty responses (use `T = void`). It does not store tokens or manage sessions.

`ApiError` exposes HTTP `status` (`null` for network failures) and `fieldErrors` containing only `loc`, `msg`, and `type`. Public string `detail` and field-validation messages from 4xx responses are preserved; validation summaries include field paths. Rejected inputs, validation context, request credentials, and original network/parser exceptions are not attached to errors. Server failures and malformed responses use safe fallback messages. Cancellation through an `AbortSignal` retains a sanitized `AbortError`.

**Verification:** `npm test` passed all 31 tests, including 20 HTTP-client cases covering JSON/form encoding, bearer headers, custom headers, empty responses, public errors, field paths, malformed errors, server failures, network/response-stream failures, and cancellation. `npm run lint` and `npm run build` passed. Vite required running tests/build outside the sandbox after its child-process startup was blocked with `spawn EPERM`. HTTP tests use mocked fetch responses; real-backend feature integration begins in later steps.

## 3. Authentication — completed

Implement login, load the current user through `/users/me/`, and protect application routes. Add a small authentication context, logout, and handling for expired credentials. Then add registration and direct successful registrants to login.

Persist the access token so page reloads preserve login until the token expires. Restore the current user through `/users/me/` before opening protected screens. The backend has no token-refresh endpoint. Clear user-specific cached data on logout or session expiry when caching is introduced.

**Done when:** valid credentials enter the application, incorrect credentials show a useful error, protected routes require authentication, and logout/expiry removes the session. Registration displays backend validation and duplicate-account errors.

**Implemented:** `/login` sends form-encoded credentials to `/auth/login`, then loads `/users/me/` with the bearer token before opening the application. `/register` sends JSON account fields to `/auth/register`, displays backend field-validation and duplicate-account errors, and directs successful registrants to login. Both forms provide labels, required fields, submission feedback, and cancellation when leaving the form. Jobs and Workers routes require authentication; login returns to the requested application URL, including its query and fragment. The header shows the current user's name and username with a Sign out action.

`src/auth.tsx` saves only the access token in local storage; passwords and current-user details are not persisted. Page reloads validate the saved token's expiry and reload `/users/me/`, keeping protected routes in a loading state until validation completes. Expired/malformed tokens and current-user authentication rejections clear the saved session. Network/server failures preserve the token and offer a retry. Logout and JWT expiry remove the token and abort authenticated requests; expiry is also checked when the window regains focus or visibility. Future feature calls should use `useAuth().request`, which supplies the bearer token and clears the session on a backend 401. Reading the JWT expiry only schedules local logout; the backend remains responsible for authentication and authorization. No data cache or refresh-token behavior is introduced.

**Try it:** configure `.env.compose` following the [quickstart](../../docs/quickstart.md#1-configure-the-stack), then run this from the repository root:

```powershell
docker compose --env-file .env.compose up --build --wait --wait-timeout 120 frontend
```

Open `http://localhost:8080`, choose Create an account if needed, then sign in. You can navigate the interface, but Jobs, submission, details, and Workers remain labeled placeholders until later steps. Reloading the page preserves login until the token expires or you sign out. For hot reload, start the backend on port 8000 and run `npm run dev` from `frontend/`, then open Vite's printed URL.

**Verification:** `npm test` passed all 63 tests, including reload persistence, current-user revalidation, restored-token expiry, malformed/expired stored tokens, authentication rejection, restoration retry after network/server failures, cancellation during restoration, and React StrictMode. Existing authentication, registration, navigation, and HTTP-client tests also pass. `npm run lint` and `npm run build` passed. Tests/build ran outside the sandbox because Vite requires child-process access. Tests mock the API; a live-backend/browser walkthrough was not performed for the persistence change. No backend changes are required.

## 4. Job submission

Implement job type, JSON-object parameters, and a private access policy. Generate an idempotency key for each intended submission and keep the same key and payload when retrying after an uncertain response. Prevent duplicate in-flight submissions and navigate to the returned job.

**Done when:** malformed JSON and non-object input are rejected before submission, API validation is visible, and a network retry preserves the submission identity. An explicit new submission receives a new key; editing a rejected request does not silently reuse an old key with changed content.

## 5. Job details and the first complete flow

Display status, job/creator IDs, type, parameters, result/error, and paginated execution attempts. Add TanStack Query for server data and polling. Refresh pending/running job details every few seconds while visible; stop polling terminal jobs. Refresh attempt history alongside the job so the final outcome appears there too.

**Done when:** accessible jobs render, missing/inaccessible jobs show a useful unavailable state, and polling stops on completion. Run the full demonstration: login, submit an `add_numbers` job, process it with the independent [example worker](../../docs/example-worker.md), and observe the stored result.

This is the first useful end-to-end checkpoint. Claiming and execution remain in the external worker.

## 6. Jobs browsing

Make Jobs the default authenticated screen. Add a paginated table, status/type filters, a Submit job action, and links to details. Keep filters and pagination in URL query parameters; reset the offset when filters change.

**Done when:** refresh and browser navigation preserve the selected view. Loading, empty, filtered-empty, and failure states are clear. Pagination follows the API's array response without inventing a total count or global statistics.

## 7. Workers browsing and registration

Add the accessible-worker list, type filtering, pagination, details, and registration. Begin registration with a private visibility policy. Show metadata and supported types. Display the newly generated API key once, with an explicit copy action and instructions to save it for the independent worker.

**Done when:** users can register and inspect workers, duplicate-name errors are useful, and keys never appear in list/detail views or persistent browser storage. Label `active` as credential/registration status; it does not establish that a process is online.

## 8. Remaining access policies

Extend job submission and worker registration with their supported policies and conditional ID inputs. Explain the selected policy beside its controls. Validate positive IDs and surface backend errors for missing records.

**Done when:** only applicable grant lists are submitted and the UI distinguishes user read access, worker claim access, and worker metadata visibility. Use explicit IDs where needed: the current API has no general user directory for a searchable user picker. Job detail responses do not expose their permission policy or grant lists.

## 9. Usability and verification review

Review keyboard navigation, labels, focus, text contrast, responsive layouts, readable JSON, copy feedback, and quiet refresh behavior. Verify recovery from API failures and credential expiry. Continue focused tests for each flow using one small frontend test setup introduced with the first behavior that needs it.

**Done when:** configured frontend tests, `npm run lint`, and `npm run build` pass; the real-backend submission/result flow works; and browser checks confirm direct navigation to implemented routes. Record commands run and any verification limits with the change.

## Deferred work

Dark mode is an optional later theme. Global statistics, worker liveness, retries, cancellation, editing/deletion, API-key rotation, scheduling, and live notifications depend on explicit requirements and backend support. Add them as separate increments when appropriate.

Keep the current Vite application and HTTP boundary. A server-rendering framework, global state store, large design system, additional infrastructure, and speculative abstraction layers are unnecessary for the proposed scope.
