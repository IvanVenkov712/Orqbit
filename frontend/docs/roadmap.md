# Frontend roadmap

Remaining work for Orqbit's operational dashboard. The [development guide](development.md) records the proposed architecture and visual design; the [API reference](../../docs/api.md) records the implemented backend contract.

The frontend is still very primitive and probably needs a redesign. The existing screens provide a functional foundation, but their visual design and user experience need further work. Treat the current design as provisional.

Treat each milestone as a separate change, splitting it further when necessary. Prefer changes to one to three files; explain additional files when directly necessary. Add dependencies only when their behavior is introduced. Each behavior change should include focused verification, rather than postponing testing until the final milestone.

## 6. Jobs browsing — remaining type filtering

Add a job-type filter to the jobs list. Keep the filter in URL query parameters and reset the offset when it changes.

**Done when:** refresh and browser navigation preserve the selected type alongside the status view. Loading, filtered-empty, and failure states are clear. Pagination follows the API's array response without inventing a total count or global statistics.

## 9. Usability and verification review

Review keyboard navigation, labels, focus, text contrast, responsive layouts, readable JSON, copy feedback, and quiet refresh behavior. Verify recovery from API failures and credential expiry. Continue focused tests for each flow using the existing frontend test setup.

**Done when:** configured frontend tests, `npm run lint`, and `npm run build` pass; the real-backend submission/result flow works; and browser checks confirm direct navigation to implemented routes. Record commands run and any verification limits with the change.

## 10. Redesign direction and screen planning

Review the current submission, job monitoring, and worker registration flows. Identify confusing navigation, weak visual hierarchy, crowded layouts, and unclear actions. Sketch a revised application layout and representative Jobs, job details, and submission screens before implementing the redesign.

**Done when:** the proposed direction covers desktop and narrow screens, makes primary actions clear, and records concrete improvements in the development guide. Keep the design within the existing API's capabilities.

## 11. Application layout and visual consistency

Apply the chosen direction to navigation, page structure, typography, spacing, colors, and shared controls. Improve tables, status indicators, forms, and feedback states using the existing styling approach. Split implementation into small changes rather than replacing every screen at once.

**Done when:** implemented screens share a consistent visual hierarchy, navigation remains clear at narrow widths, and keyboard focus and text contrast remain usable. Preserve existing routes, URL filters, and application behavior.

## 12. Workflow refinement and redesign verification

Refine job submission and its nested parameter editor, job details and attempt history, and worker registration with its one-time API-key display. Make long JSON values, validation errors, loading states, empty results, and recovery actions easier to understand. Apply the revised design to login and registration as well.

**Done when:** users can sign in, submit a job, follow its outcome, inspect attempt history, and register a worker without unclear next steps. Repeat the usability checks from step 9 after the redesign, run the configured tests, lint, and build, and verify the main flows against the real backend and independent worker.

## Deferred work

Browsing all accessible workers remains deferred. Dark mode is an optional later theme. Global statistics, worker liveness, retries, cancellation, editing/deletion, API-key rotation, scheduling, and live notifications depend on explicit requirements and backend support. Add them as separate increments when appropriate.

Keep the current Vite application and HTTP boundary. A server-rendering framework, global state store, large design system, additional infrastructure, and speculative abstraction layers are unnecessary for the proposed scope.
