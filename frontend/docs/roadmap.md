# Frontend roadmap

Build a small operational dashboard around Orqbit's existing public HTTP API. Prioritize a complete submission-and-result flow, then add browsing and management screens. The [development guide](development.md) records the proposed architecture and visual design; the [API reference](../../docs/api.md) records the implemented backend contract.

## Current state

The frontend contains a React/TypeScript application shell with React Router, a light responsive layout, Jobs/Workers navigation, a signed-out user area, and explicitly labeled route placeholders. Vite and Nginx proxy `/api` to the backend. Docker Compose includes a frontend service on port 8080.

Step 1 is implemented; steps 2–9 remain planned. Vitest, jsdom, and React Testing Library provide focused component tests through `npm test`. Authentication, API integration, feature screens, and TanStack Query are not implemented yet.

Treat each milestone as a separate change, splitting it further when necessary. Prefer changes to one to three files; explain additional files when directly necessary. Add dependencies only when their behavior is introduced. Each behavior change should include focused verification, rather than postponing testing until the final milestone.

## 1. Application shell and visual foundation — completed

Replace the starter content with a simple layout. Introduce React Router, navigation for Jobs and Workers, a current-user area, and route placeholders. Establish the light palette, typography, spacing, controls, and focus styles from the development guide.

**Done when:** navigation and browser back/forward work, unknown routes have a useful response, and the layout works at narrow widths. Keep placeholders clearly identified until their screens exist.

**Implemented:** `/` redirects to `/jobs`. The Jobs, submission, job details, Workers, worker details, login, and registration routes render labeled placeholders. Navigation highlights the current section, including detail routes. Unknown routes offer a link back to Jobs. Shared styles establish the guide's light palette, typography, spacing, controls, keyboard focus, and skip link. The current-user area explicitly shows “Not signed in” until authentication is implemented.

**Verification:** `npm test` passed all 11 routing/component tests, including browser history, direct route entry, active navigation, placeholder links, and unknown-route recovery. `npm run lint` and `npm run build` passed. Headless Edge checks confirmed navigation, browser back/forward, direct reload, unknown-route recovery, visible keyboard focus on the skip link, and no horizontal overflow at 320px, 390px, and 1280px. Direct route requests to the Vite server returned the application shell. No backend integration is introduced in this step.

## 2. Shared HTTP client

Add `src/api/client.ts` for `/api` requests, bearer authentication, response parsing, and meaningful errors. Support JSON and form-encoded bodies. Define request/response types beside each feature when needed; keep transport concerns out of page components.

**Done when:** the client handles success, network failures, string API errors, and field-validation errors. Login can send form data without an incorrect JSON content type. Credentials and raw internal errors are not exposed in diagnostics or the UI.

## 3. Authentication

Implement login, load the current user through `/users/me/`, and protect application routes. Add a small authentication context, logout, and handling for expired credentials. Then add registration and direct successful registrants to login.

Start with an in-memory session: refreshing the page requires login again. The backend has no token-refresh endpoint. Clear user-specific cached data on logout or session expiry when caching is introduced.

**Done when:** valid credentials enter the application, incorrect credentials show a useful error, protected routes require authentication, and logout/expiry removes the session. Registration displays backend validation and duplicate-account errors.

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
