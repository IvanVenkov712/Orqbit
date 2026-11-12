<h1 align="center">Orqbit</h1>

<p align="center">
  <img src="assets/orqbit-icon.svg" alt="Orqbit icon" width="192" height="192" />
</p>

**Submit work. Process it independently. Track the outcome.**

Orqbit is a platform for asynchronous job processing, with a FastAPI backend and a browser interface. It connects producer applications that need work done with independent workers that know how to do it, giving both a shared HTTP API for submitting, claiming, and tracking jobs.

A client submits a job with a type and parameters, receives its identity, and can check its progress or retrieve the result later. Workers request compatible jobs when they are ready, execute them in their own processes, and report success or failure. PostgreSQL keeps the job data, ownership, execution attempts, and outcomes together.

This makes Orqbit a foundation for moving time-consuming work out of the request-response cycle while keeping its progress visible to the application and its users.

## Why Orqbit?

Generating a report, transforming a dataset, or processing a file can take longer than an application should keep an HTTP request open. Moving that work to another process introduces a second problem: the application still needs to know what was submitted, who is processing it, and how it ended.

Orqbit brings that coordination into one place. Its development centers on a clear job lifecycle, persistent state, and explicit ownership. The aim is to make background processing understandable and useful: applications describe the work, workers provide the execution logic, and Orqbit connects the two.

The project also explores how far a focused HTTP API and PostgreSQL can take job coordination. Keeping the queue and its records in the same database makes the relationships between jobs, workers, permissions, and results easier to inspect and reason about.

## How it works

1. **Submit a job.** An authenticated client provides a job type, JSON parameters, and an access policy.
2. **Keep it in the queue.** Orqbit persists the job so its status can be queried independently of the original request.
3. **Claim compatible work.** A registered worker requests a job matching its declared capabilities and permissions. Concurrent workers can claim different jobs safely.
4. **Execute independently.** The worker performs the task outside the API process, renews its attempt lease as needed, and reports the outcome before the lease expires.
5. **Retrieve the outcome.** The client reads the job's status and, when available, its result or error.

```text
PENDING -> RUNNING -> SUCCEEDED
                  \-> FAILED
```

For example, the included `add_numbers` worker turns `{"numbers":[2,3,5]}` into `{"sum":10}`. It demonstrates the full flow, from submission to a stored result, and provides a starting point for writing a worker for another job type.

## Features

- **Job submission and tracking.** Submit typed jobs with JSON parameters and retrieve their status, results, errors, and execution attempt IDs.
- **Idempotent submission.** Creator-scoped submission keys return the existing job for matching requests and reject conflicting reuse.
- **Capability-based dispatch.** Workers declare the job types they support and pull compatible work when ready.
- **Concurrent claiming.** Atomic claims coordinate access to pending jobs so competing workers do not receive the same job simultaneously.
- **Owned outcome reporting.** Only the worker assigned to an attempt can report its success or failure; exact replays of accepted reports are safe.
- **Execution leases and attempt heartbeats.** Workers can renew an owned running attempt through the API. Expired leases reject new outcomes, and a separate recovery process closes abandoned attempts. See the [lease protocol](docs/api.md#attempt-heartbeats-and-leases).
- **Bounded retries for lost attempts.** Jobs save an attempt limit from configuration; recovery schedules retries with capped backoff and preserves earlier attempts. Retries are disabled by default. See [recovery and bounded retries](docs/api.md#recovery-and-bounded-retries).
- **Authentication and access policies.** User bearer tokens, separate worker/producer API keys, and access policies control who can submit, view, or claim work. Owners can reissue keys; producer registrations can also be deactivated.
- **Producer applications.** Registered producers submit and read their own jobs through dedicated API routes. CLI and interactive console examples demonstrate submission keys, status polling, and explicit retry behavior.
- **Searchable job and worker lists.** Filter and paginate records to find relevant work and registered workers.
- **Persistent execution records.** PostgreSQL stores job parameters, attempt ownership, timestamps, and outcomes. An authorized, paginated history endpoint exposes attempt details.
- **Independent example workers.** Addition, prime counting, CSV statistics, and delay examples each have their own dependencies, configuration, and tests.
- **Browser interface.** Submit jobs, inspect outcomes and attempt history, browse accessible jobs/workers with filters and sorting, and manage producer registrations.

## What this approach offers

**Responsive applications.** Clients can submit work and return to other tasks while execution happens in a separate process. Progress and results remain available through the API.

**Independent workers.** Each worker can have its own dependencies, configuration, and deployment. The HTTP boundary allows execution logic to evolve separately from the server and lets worker applications use a different technology stack.

**A shared view of work.** Job state, access rules, and outcomes live in one place, giving clients and workers a consistent record to consult.

**A focused infrastructure footprint.** The API and PostgreSQL provide the coordination layer without requiring a separate message broker. Workers remain ordinary applications that communicate over HTTP.

## Where it fits

Orqbit's job-and-worker model can support workloads such as report generation, data transformation, document processing, and integrations with external services. Each workload needs a worker that implements its job type; included examples handle numeric addition, prime counting, CSV statistics, and lease demonstrations.

It is particularly useful when the application needs a persistent record of submitted work and its outcome, and when different kinds of work belong in independently managed worker applications.

## Planned extensions

The next areas of development build on the existing submission, claiming, and reporting flow:

- **Worker process liveness and hard execution deadlines** to complement the implemented per-attempt leases, heartbeats, and recovery.
- **Retry classification and manual replay** to extend the current lost-attempt retry policy to explicitly retryable worker failures and authorized replay.
- **Operational visibility** through metrics, structured logs, and tools for diagnosing stalled or failed work.
- **Additional job controls and integrations**, such as cancellation, scheduling, priorities, and completion webhooks, as their requirements take shape.

Follow the [backend roadmap](docs/roadmap.md) and [frontend roadmap](frontend/docs/roadmap.md) for remaining tasks, or use the [remaining-work index](docs/status.md).

## Try Orqbit

New to Orqbit? Follow the [step-by-step tutorial](tutorials/getting-started/README.md) for a beginner-friendly walkthrough with screenshots, from installation and account setup to running workers, submitting jobs, and reading results. To build a worker for longer tasks, follow [Build a worker with leases and heartbeats](tutorials/worker-leases-and-heartbeats/README.md). Browse both guides in the [tutorial index](tutorials/README.md).

Start with the [Docker Compose quickstart](docs/quickstart.md) to run the API and PostgreSQL, authenticate, and submit a job. It requires Git and Docker in Linux-container mode; Python and PostgreSQL do not need to be installed on the host.

Then follow the [example worker guide](examples/workers/add_numbers/README.md) to process an `add_numbers` job and retrieve its result. Interactive API documentation is available at `http://127.0.0.1:8000/docs` once the API is running.

The backend uses **Python, FastAPI, PostgreSQL, SQLAlchemy, Pydantic, and Alembic**. For running Python directly on your host, see the [development guide](docs/development.md#running-the-api-locally).

## Documentation

| Guide | Contents |
| --- | --- |
| [Quickstart](docs/quickstart.md) | Docker setup and an authenticated submission walkthrough |
| [Add numbers worker](examples/workers/add_numbers/README.md) | Basic job execution, configuration, and tests |
| [Delay worker](examples/workers/delay/README.md) | Configurable delay without heartbeat |
| [Delay with heartbeat](examples/workers/delay_with_heartbeat/README.md) | Long execution with lease renewal and ownership checks |
| [Count primes worker](examples/workers/count_primes/README.md) | CPU computation in batches with cooperative heartbeat checks |
| [CSV summary worker](examples/workers/csv_summary/README.md) | Numeric column statistics from CSV text |
| [CLI producer](examples/producers/add_numbers_cli/README.md) | One-shot submission, explicit key reuse, and optional bounded waiting |
| [Console producer](examples/producers/add_numbers_console/README.md) | Continuous input, background submission/polling, and in-memory retries |
| [API reference](docs/api.md) | Authentication, permissions, requests, responses, and errors |
| [Development](docs/development.md) | Local setup, repository layout, coordination details, migrations, and containers |
| [Testing](docs/testing.md) | PostgreSQL integration tests and container verification |
| [Remaining work](docs/status.md) | Backend/frontend tasks, outstanding requirements, and open decisions |
| [Backend roadmap](docs/roadmap.md) | Remaining implementation and operational work |
| [Architecture](docs/architecture.md) | Implemented components, coordination guarantees, recommended worker/producer structures, and open decisions |
| [Requirements](docs/requirements.md) | Outstanding acceptance criteria, distinct from implemented behavior |
| [Frontend](frontend/README.md) | Browser features, local setup, and interface development |

## License

[MIT](LICENSE).
