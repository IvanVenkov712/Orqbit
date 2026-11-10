# Frontend roadmap

Remaining work for Orqbit's operational dashboard. The [development guide](development.md) records the proposed architecture and visual design; the [API reference](../../docs/api.md) records the implemented backend contract.

Treat each milestone as a separate change, splitting it further when necessary. Prefer changes to one to three files; explain additional files when directly necessary. Add dependencies only when their behavior is introduced. Each behavior change should include focused verification, rather than postponing testing until the final milestone.

## 6. Jobs browsing — remaining type filtering

Add a job-type filter to the jobs list. Keep the filter in URL query parameters and reset the offset when it changes.

**Done when:** refresh and browser navigation preserve the selected type alongside the status view. Loading, filtered-empty, and failure states are clear. Pagination follows the API's array response without inventing a total count or global statistics.

## 9. Usability and verification review

Review keyboard navigation, labels, focus, text contrast, responsive layouts, readable JSON, copy feedback, and quiet refresh behavior. Verify recovery from API failures and credential expiry. Continue focused tests for each flow using the existing frontend test setup.

**Done when:** configured frontend tests, `npm run lint`, and `npm run build` pass; the real-backend submission/result flow works; and browser checks confirm direct navigation to implemented routes. Record commands run and any verification limits with the change.

## Deferred work

Browsing all accessible workers remains deferred. Dark mode is an optional later theme. Global statistics, worker liveness, retries, cancellation, editing/deletion, API-key rotation, scheduling, and live notifications depend on explicit requirements and backend support. Add them as separate increments when appropriate.

Keep the current Vite application and HTTP boundary. A server-rendering framework, global state store, large design system, additional infrastructure, and speculative abstraction layers are unnecessary for the proposed scope.
