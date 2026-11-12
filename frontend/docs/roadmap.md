# Frontend roadmap

The current interface includes the sidebar layout, nested parameter editor, accessible jobs/workers across owners, type/owner/date/status filters, URL-persisted sorting and page grouping, lost-attempt views, and producer management (search, registration, key reissue, deactivation, and safe deletion). These are implemented features, not pending milestones. Worker key reissue/type updates/deletion exist in the backend but do not yet have browser controls.

## 1. Retry visibility

- Show `attempts_count`, `max_attempts`, and `available_at` on job details.
- Explain when a pending job is waiting for its retry time and when its attempt budget is exhausted.
- Make transitions between running, retry-waiting, and terminal states clear without adding new API statuses or client-side retry controls.
- Verify polling and attempt-history refresh across reassignment and final outcomes.

## 2. Usability and accessibility follow-up

- Review submission, job monitoring, attempt history, and worker registration for unclear actions, crowded layouts, and weak visual hierarchy.
- Validate the existing desktop and narrow layouts with real use before planning further visual changes.
- Improve the nested parameter editor, long JSON values, validation messages, empty/error states, and one-time API-key display.
- Review keyboard navigation, labels, focus, contrast, copy feedback, reduced motion, and quiet background refresh.

## 3. Browser and integration verification

- Verify sign-in, submission, execution by an independent worker, result retrieval, retry history, and worker registration against the real backend.
- Verify producer registration, key replacement, deactivation, and deletion constraints against the real backend and independent producer examples.
- Check direct route loading, expired credentials, network/API failures, and narrow layouts in a browser.
- Run the configured frontend tests, lint, and production build for interface changes.

## Deferred interface work

Evaluate as separate increments:

- Optional job-type suggestions using `GET /job-types`.
- User/grant pickers using `GET /users` and `GET /users/{id}`.
- Owner-only browser controls for existing worker supported-type updates, key reissue, and deletion, with one-time secret display and conflict feedback.
- Optional dark mode and further presentation of operational metrics.
- Controls for manual replay, cancellation, job editing/deletion, worker deactivation, producer reactivation, scheduling, and notifications after their backend contracts are defined.

Use the [API reference](../../docs/api.md) for public contracts and the [development guide](development.md) for setup and working conventions.
