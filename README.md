# Orqbit

**Submit work. Process it independently. Track the outcome.**

Orqbit is a backend platform for asynchronous job processing. It connects applications that need work done with independent workers that know how to do it, giving both a shared HTTP API for submitting, claiming, and tracking jobs.

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
4. **Execute independently.** The worker performs the task outside the API process and reports the outcome for its assigned execution attempt.
5. **Retrieve the outcome.** The client reads the job's status and, when available, its result or error.

```text
PENDING -> RUNNING -> SUCCEEDED
                  \-> FAILED
```

For example, the included `add_numbers` worker turns `{"numbers":[2,3,5]}` into `{"sum":10}`. It demonstrates the full flow, from submission to a stored result, and provides a starting point for writing a worker for another job type.

## Features

- **Job submission and tracking.** Submit typed jobs with JSON parameters and retrieve their status, results, errors, and execution attempt IDs.
- **Capability-based dispatch.** Workers declare the job types they support and pull compatible work when ready.
- **Concurrent claiming.** Atomic claims coordinate access to pending jobs so competing workers do not receive the same job simultaneously.
- **Owned outcome reporting.** Only the worker assigned to an attempt can report its success or failure.
- **Authentication and access policies.** User authentication, individual worker API keys, and permission-aware access control who can view or claim work.
- **Searchable job and worker lists.** Filter and paginate records to find relevant work and registered workers.
- **Persistent execution records.** PostgreSQL stores job parameters, attempt ownership, timestamps, and outcomes.
- **An independent example worker.** A runnable application with its own dependencies, configuration, and tests shows how to integrate through the public API.

## What this approach offers

**Responsive applications.** Clients can submit work and return to other tasks while execution happens in a separate process. Progress and results remain available through the API.

**Independent workers.** Each worker can have its own dependencies, configuration, and deployment. The HTTP boundary allows execution logic to evolve separately from the server and lets worker applications use a different technology stack.

**A shared view of work.** Job state, access rules, and outcomes live in one place, giving clients and workers a consistent record to consult.

**A focused infrastructure footprint.** The API and PostgreSQL provide the coordination layer without requiring a separate message broker. Workers remain ordinary applications that communicate over HTTP.

## Where it fits

Orqbit's job-and-worker model can support workloads such as report generation, data transformation, document processing, and integrations with external services. Each workload needs a worker that implements its job type; the included example handles numeric addition.

It is particularly useful when the application needs a persistent record of submitted work and its outcome, and when different kinds of work belong in independently managed worker applications.

## Planned extensions

The next areas of development build on the existing submission, claiming, and reporting flow:

- **Worker heartbeats and execution leases** to detect abandoned work and support recovery after worker failures.
- **Retry policies with backoff** to handle transient failures with explicit attempt limits.
- **Detailed attempt history** to make previous executions and their outcomes available through the API.
- **Operational visibility** through metrics, structured logs, and tools for diagnosing stalled or failed work.
- **Additional job controls and integrations**, such as cancellation, scheduling, priorities, and completion webhooks, as their requirements take shape.

These are planned capabilities. The [roadmap](docs/roadmap.md) describes the proposed stages; [implementation notes](docs/status.md) document guarantees, limitations, and recorded verification.

## Try Orqbit

Start with the [Docker Compose quickstart](docs/quickstart.md) to run the API and PostgreSQL, authenticate, and submit a job. It requires Git and Docker in Linux-container mode; Python and PostgreSQL do not need to be installed on the host.

Then follow the [example worker guide](docs/example-worker.md) to process an `add_numbers` job and retrieve its result. Interactive API documentation is available at `http://127.0.0.1:8000/docs` once the API is running.

The backend uses **Python, FastAPI, PostgreSQL, SQLAlchemy, Pydantic, and Alembic**. For running Python directly on your host, see the [development guide](docs/development.md#running-the-api-locally).

## Documentation

| Guide | Contents |
| --- | --- |
| [Quickstart](docs/quickstart.md) | Docker setup and an authenticated submission walkthrough |
| [Example worker](docs/example-worker.md) | Worker setup, configuration, execution, and checks |
| [API reference](docs/api.md) | Authentication, permissions, requests, responses, and errors |
| [Development](docs/development.md) | Local setup, repository layout, coordination details, migrations, and containers |
| [Testing](docs/testing.md) | PostgreSQL integration tests and container verification |
| [Implementation notes](docs/status.md) | Behavior, limitations, and verification records |
| [Roadmap](docs/roadmap.md) | Development stages and planned capabilities |
| [Architecture](docs/architecture.md) and [requirements](docs/requirements.md) | Proposed reliability model and design criteria |

## License

[MIT](LICENSE).
