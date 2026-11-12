# Frontend roadmap

## 1. Job-type filtering

- Add a job-type filter to the jobs list.
- Keep the selected type in URL query parameters alongside status and pagination; reset the offset when filters change.
- Cover browser navigation, filtered-empty results, loading, and failures with focused tests.

## 2. Retry visibility

- Show `attempts_count`, `max_attempts`, and `available_at` on job details.
- Explain when a pending job is waiting for its retry time and when its attempt budget is exhausted.
- Make transitions between running, retry-waiting, and terminal states clear without adding new API statuses or client-side retry controls.
- Verify polling and attempt-history refresh across reassignment and final outcomes.

## 3. Usability and redesign

- Review submission, job monitoring, attempt history, and worker registration for unclear actions, crowded layouts, and weak visual hierarchy.
- Sketch a revised layout and representative Jobs, details, and submission screens for desktop and narrow widths.
- Apply the chosen navigation, typography, spacing, colors, tables, forms, and feedback patterns in small changes.
- Improve the nested parameter editor, long JSON values, validation messages, empty/error states, and one-time API-key display.
- Review keyboard navigation, labels, focus, contrast, copy feedback, reduced motion, and quiet background refresh.

## 4. Browser and integration verification

- Verify sign-in, submission, execution by an independent worker, result retrieval, retry history, and worker registration against the real backend.
- Check direct route loading, expired credentials, network/API failures, and narrow layouts in a browser.
- Run the configured frontend tests, lint, and production build for changes and after the redesign.

## Deferred interface work

Evaluate as separate increments:

- Optional job-type suggestions using `GET /job-types`.
- User/grant pickers using `GET /users` and `GET /users/{id}`.
- Browsing shared jobs and all accessible workers, with explicit ownership/access presentation.
- Optional dark mode and further presentation of operational metrics.
- Controls for manual replay, cancellation, editing/deletion, key rotation, scheduling, and notifications after their backend contracts are defined.

Use the [API reference](../../docs/api.md) for public contracts and the [development guide](development.md) for setup and working conventions.
