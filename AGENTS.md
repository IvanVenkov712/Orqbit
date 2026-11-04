# AGENTS.md — Orqbit

## Project overview

**Orqbit** is a backend platform for reliable asynchronous job processing.

Clients submit jobs through an HTTP API. Independent workers request (pull/claim) jobs they are capable of executing, perform the work outside the API process, and report their outcome. Clients can query job status and retrieve results without keeping their original HTTP request open.

This is primarily a **learning and portfolio project**. Prioritize clear architecture, correctness, maintainability, and understandable trade-offs over feature count or production-scale complexity.

## Minimal-change policy

This is a learning project. Make the smallest understandable change that
satisfies the explicit request.

- Do not treat a task as permission to complete the surrounding milestone.
- Before editing, briefly list the files you expect to change and why.
- Prefer 1–3 files. Additional files must be directly necessary for the request.
- Use existing files and patterns. Do not add layers, helpers, services, or
  abstractions merely to separate a few lines of code.
- Add focused tests for the requested behavior. Reuse the existing test setup.
  Do not create additional smoke scripts or testing infrastructure unless asked.
- Update one relevant documentation location when needed. Do not synchronize
  or rewrite README, status, roadmap, and development docs for every change.
- Do not change CI, Docker, dependencies, or configuration unless the task
  requires it.
- Do not include unrelated cleanup, formatting, lint fixes, or refactoring.
- Mention optional improvements separately instead of implementing them.
- If scope must expand, explain the concrete necessity before proceeding.
- When asked for an explanation or review, do not edit files.

Prefer a small, clear solution with stated limitations over a comprehensive
solution with extra machinery.

## Current architecture and technology

- **Language:** Python.
- **API:** FastAPI.
- **Persistence:** PostgreSQL with SQLAlchemy 2.x ORM.
- **Schema migrations:** Alembic, when migrations are introduced.
- **Validation:** Pydantic models for API input/output.
- **Workers:** independent processes/services that interact with Orqbit through the API.
- **Job dispatch:** pull-based; workers ask for compatible pending jobs.
- **Initial queue:** PostgreSQL-backed jobs, not an external message broker.

Treat these as the intended direction, not proof that every component is already installed. Inspect the repository before using or changing its dependencies or structure.

## Core workflow

1. A client submits a job with a **job type** and JSON-compatible **parameters**.
2. Orqbit validates and persists it with a `PENDING` status.
3. A worker supplies its supported job types and requests a job.
4. Orqbit **atomically claims** one compatible pending job and records ownership / relevant timestamps.
5. The worker executes the job independently.
6. The worker reports success with a JSON-compatible result, or failure with an error description.
7. Orqbit persists the terminal state; clients can retrieve status and result via the API.

Initial lifecycle:

```text
PENDING -> RUNNING -> SUCCEEDED
                   \-> FAILED
```

Use the status names already present in the codebase if they differ. Cancellation, retries, leases, heartbeats, deadlines, priorities, callbacks/webhooks, and push-based assignment are **future extensions**, not default MVP requirements.

## Architectural rules

1. **Keep it simple.** Prefer a small modular monolith for the API and database, plus independent workers. Do not introduce microservices, RabbitMQ, Kafka, Celery, a custom event bus, or an event-driven architecture without a concrete requirement.
2. **Keep responsibilities separate.** HTTP endpoints handle transport, validation, and responses. Application/service functions implement job lifecycle operations. Repositories/data-access code handles persistence. ORM entities are not API contracts.
3. **Workers are independent.** The server stores and coordinates jobs; it does not import or directly execute worker-specific business logic.
4. **Make claiming safe.** Never implement claim as an unprotected SELECT followed by UPDATE. When concurrency work is in scope, use a single transaction with appropriate PostgreSQL row locking (e.g. `FOR UPDATE SKIP LOCKED`) or an equally safe atomic approach. Do not prematurely add distributed locking.
5. **Explicit ownership and transitions.** Only the worker that owns a running job should be able to report its outcome. Validate allowed state transitions. If the current model cannot enforce ownership, flag that gap rather than silently assuming it can.
6. **PostgreSQL is the source of truth.** Keep job parameters and results in PostgreSQL (JSONB is suitable for JSON-compatible values). Do not add paid storage services or an external queue by default.
7. **Do not block API requests on job execution.** API operations should accept, claim, inspect, or update jobs; actual job execution happens in workers.
8. **Reliability is incremental.** Preserve persisted jobs and consistent state first. Add crash recovery, retry policies, leases, and delivery guarantees only with explicit specifications and tests.
9. **Avoid overengineering.** Do not introduce generic plugin systems, abstraction layers, excessive inheritance, dependency-injection frameworks, or speculative extensibility.

## Data model guidance

A job will typically need:

- A unique identifier.
- `job_type` (what kind of work is requested).
- `params` (JSON-compatible input).
- `status`.
- `result` (nullable JSON-compatible output).
- An optional error description.
- Creation and update timestamps; execution timestamps where justified.
- Worker/claim ownership metadata when implementing safe completion reporting.

This is guidance, **not a command to rewrite the existing schema**. Check actual models and migrations before proposing changes. Index job lookup fields when warranted by query patterns.

## API conventions

- Use resource-oriented REST endpoints with consistent request/response schemas.
- Return appropriate HTTP status codes and meaningful, structured errors.
- Validate job types, parameters, state transitions, and worker-reported results at the API boundary.
- Keep internal stack traces and secrets out of HTTP responses.
- Do not invent endpoints or change public contracts without identifying compatibility implications.
- Prefer clear names and straightforward control flow over clever helpers.

Potential API surface (adapt to existing routes):

```text
POST /jobs                 Submit a job
GET  /jobs/{job_id}        Read status, metadata, and result
POST /jobs/claim           Worker claims a compatible job
POST /jobs/{job_id}/complete  Worker reports success
POST /jobs/{job_id}/fail      Worker reports failure
```

A no-job response from claim must be unambiguous (for example, `204 No Content`). Do not treat these illustrative routes as fixed if the repository already uses others.

## Python, SQLAlchemy, and database practices

- Prefer readable, typed Python and modern SQLAlchemy 2.x patterns (`select()`, `Session`, mapped models).
- Use SQLAlchemy expressions (`and_()` or multiple `.where()` criteria), **not Python `and`**, to combine SQL predicates.
- Keep transactions short and define commit/rollback ownership clearly.
- Do not hold a database transaction open while a worker performs the job.
- Handle uniqueness, integrity, and concurrent update failures deliberately.
- Avoid N+1 queries where relationships are loaded; choose eager loading only where needed.
- Make schema changes through Alembic migrations rather than silently changing deployed tables.
- Do not assume an async SQLAlchemy session is required merely because FastAPI supports `async def`. Choose sync or async database access consistently with the existing project setup.

## Tests and verification

For each behavior change, add or update focused tests. Prioritize:

- Job submission and invalid payloads.
- Claim eligibility by supported job type.
- Empty-queue behavior.
- Successful and failed completion.
- Rejection of invalid state transitions.
- Worker ownership validation, once implemented.
- Concurrent claims: two workers must **never receive the same job simultaneously**.
- Persistence and transaction rollback behavior.

Use PostgreSQL-backed integration tests for PostgreSQL-specific locking/JSONB behavior; SQLite is not a faithful substitute for concurrency semantics. Prefer deterministic tests to arbitrary sleeps.

Before finishing a change, run the relevant tests, formatters, and linters **if configured in the repository**. Report which commands ran and which could not run. Never claim a test passed without executing it.

## How coding agents should work

1. **Inspect before editing:** read the README, current code, tests, dependency files, and migrations relevant to the task.
2. **Respect the current stage:** implement the requested feature, not the entire future roadmap.
3. **Make small, cohesive changes:** favor minimal diffs and preserve existing conventions.
4. **Explain architectural decisions:** briefly state the problem, alternatives when relevant, and why the chosen design is appropriate.
5. **Do not silently redesign:** seek explicit direction before changing the worker delivery model, adding infrastructure, or replacing persistence.
6. **Be honest about guarantees:** distinguish implemented behavior from desired properties (especially atomic claiming, retries, crash recovery, and exactly-once processing).
7. **Keep documentation accurate:** update README/API docs and tests when user-facing behavior changes.
8. **Avoid unnecessary code generation:** when asked for guidance or review, provide reasoning and targeted suggestions rather than rewriting large sections unrequested.
9. **Never commit secrets:** use environment variables and examples with placeholders; do not check in credentials or production connection strings.
10. **Avoid unrelated refactors:** call out potential improvements separately instead of combining them into a feature change.

## Explicit non-goals for the initial MVP

- Executing user-submitted arbitrary Python code inside the API service.
- Built-in worker execution or centralized push scheduling.
- RabbitMQ, Kafka, Celery, or a mandatory event bus.
- Distributed orchestration, autoscaling, or Kubernetes deployment.
- Exactly-once execution guarantees.
- Complex retries, dead-letter queues, lease recovery, or scheduling before their requirements are defined.
- Real-time notification delivery to clients before a callback/polling requirement is settled.

## Future evolution

Add capabilities when they solve demonstrated problems. Likely follow-on milestones include atomic concurrent claiming, worker ownership, crash recovery via leases/heartbeats, retries with backoff, authentication, observability, and optional client notifications. Revisit external message brokers or event-driven components only if PostgreSQL-backed coordination is no longer appropriate for stated requirements.

**Guiding principle:** Make Orqbit a small, correct, understandable asynchronous job platform before trying to make it a distributed systems framework.
