# API reference

This page describes the current unversioned prototype. `/docs` and `/openapi.json` expose the generated schema while the API runs. Successful routes return HTTP 200, including registration, worker creation, and job submission. The `/v1` contract at the end is a future proposal.

## Authentication and users

| Method | Route | Authentication | Request / response |
| --- | --- | --- | --- |
| POST | `/auth/register` | None | JSON: `username`, `email`, `full_name`, `password`; returns user metadata |
| POST | `/auth/login` | None | Form fields: `username`, `password`; returns `access_token` and `token_type: "bearer"` |
| GET | `/users/me/` | User bearer token | Returns the current active user's metadata |
| GET | `/users` | User bearer token | Optional `query`, `limit`, `offset`; returns active users' public profiles |
| GET | `/users/{user_id}` | User bearer token | Returns an active user's public profile, or 404 |

User requests use `Authorization: Bearer <access_token>`. Worker claim, heartbeat, and outcome requests use `X-API-Key: <worker-api-key>`. Creating or viewing workers uses a user token. No credentials are needed for health routes.

Usernames and worker names contain 3?16 ASCII letters, digits, underscores, or hyphens. Email addresses are validated. Registration passwords contain 6?20 ASCII letters/digits or `@`, `$`, `#`, `%`, including at least one uppercase letter, lowercase letter, digit, and one of those symbols. User metadata contains `id`, `username`, `email`, `full_name`, `active`, and `role`; password hashes are not returned.

Passwords are hashed with Argon2. Tokens use the configured signing key, algorithm, and expiry. Inactive users cannot log in or access user-protected routes. Worker authentication checks its API-key hash and the worker's active flag. The current API has no account-management, token-refresh, or key-rotation endpoints.

### User discovery

Any active authenticated user can discover other active users for access-policy selection. `GET /users` returns a JSON array ordered by descending ID, including the caller when applicable. The optional `query` is a case-insensitive, literal substring of the username (1–16 characters); `%` and `_` are not wildcards. Omit it to browse all active users. Filtering happens before pagination: `limit` defaults to 50 and must be 1–100; `offset` defaults to 0 and must be nonnegative. No matches or an offset beyond the results returns 200 with `[]`; invalid parameters return 422.

Both discovery endpoints return only `id`, `username`, and `full_name`. They omit email, role, account status, and password hashes. `GET /users/{user_id}` returns 404, `User not found`, for missing or inactive users. `/users/me/` keeps its existing, fuller response for the signed-in user. Discovery does not grant access to a user's jobs or workers; existing permission policies still apply.

## Jobs

| Method | Route | Request | Response |
| --- | --- | --- | --- |
| POST | `/jobs/` | JSON: `job_type`, `params`, `permission_policy`; optional permitted-ID lists | Created job |
| GET | `/jobs` | Optional `owner_username`, `owner_id`, `status`, `job_type`, `attempt_status`, `created_from`, `created_before`, `limit`, `offset`, `sort` query parameters | Accessible job summaries, newest ID first by default |
| GET | `/jobs/{job_id}` | Job ID | Accessible job, or 404 |
| GET | `/jobs/{job_id}/attempts` | Job ID; optional `limit`, `offset` | Execution attempts, highest attempt number first |

All job routes require a user token. Job types are 1?100 characters and must contain a non-whitespace character. Types are matched as stored; they are not trimmed or normalized. `params` must be a JSON object and may contain nested JSON values. The creator comes from authentication, not a request-supplied user ID.

Submission also requires an `Idempotency-Key` header containing 1–100 characters and at least one non-whitespace character. Generate a key for each intended submission and reuse it with the same request when retrying. Keys are scoped to the authenticated creator: a matching replay returns the existing job in its current state; changed content returns 409, `Conflicting create requests`. JSON object key order and permission-list order/duplicates do not affect matching; other array ordering remains significant. Keys remain reserved while the job exists.

Migration `4610066358ca` adds the required columns and uniqueness on `(user_id, idempotency_key)`. It preserves existing jobs by assigning each a synthetic key `legacy-job:<job_id>` and the fingerprint marker `legacy` before making both columns non-nullable. Original submission keys cannot be recovered, so historical jobs do not support submission replay. Future submissions must supply their own keys; the columns have no defaults.

`GET /jobs` defaults to `limit=50`, `offset=0`; limit must be 1?100 and offset nonnegative. Filters are combined with permission checks. The optional `sort=status_updated` orders by lifecycle status (`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`), then descending update time and ID; other sort values return 422.

The list returns a JSON array of `JobSummaryRead` objects containing only `id`, `user_id`, `owner_username`, `job_type`, `status`, `created_at`, and `updated_at`. The database query fetches these job columns and the owner's username in one query and does not load attempts. No matches or an offset beyond the results returns 200 with `[]`.

Omitting owner filters lists jobs from all owners the caller can access. `owner_username` matches the exact, case-sensitive username (1–16 characters); an unknown username returns an empty list. The existing `owner_id` remains supported for API compatibility; if both are supplied, both must match. Neither filter grants access to hidden records. `attempt_status` matches jobs with **any historical attempt** in that state (`RUNNING`, `SUCCEEDED`, `FAILED`, or `LOST`) without duplicating jobs with several matching attempts. It combines with the job's current `status`, when supplied. `LOST` remains an attempt state, not a job state: a job with a lost attempt may now be pending, running, succeeded, or failed.

`created_from` is inclusive and `created_before` is exclusive, both filtering the job's creation time. Supply ISO 8601 timestamps with an explicit timezone, for example `2026-11-10T08:00:00Z`. Missing timezones, invalid timestamps, and ranges with `created_from >= created_before` return 422. All filters and permissions apply before sorting and pagination.

The frontend browses all accessible owners by default and offers an optional **Owner username** filter, exact job-type matching, local creation-time inputs, all/current-status views and a **Lost attempts** view (`attempt_status=LOST`). Filter values and pagination persist in the URL; changing filters resets the offset. Failed rows link to stored job/attempt error details; lost-attempt rows link to attempt history. Lists and detail pages display the owner's username. Detail and history pages use backend access decisions rather than rejecting records merely because their owner differs from the viewer.

**List response compatibility:** list items no longer include `params`, `result`, `error`, or `attempt_ids`. Clients needing those fields must use `GET /jobs/{job_id}`. Job submission and detail responses retain their full `JobRead` shape:

| Field | Meaning |
| --- | --- |
| `id`, `user_id` | Integer job and creator IDs |
| `owner_username` | Creator's username |
| `job_type`, `params` | Submitted type and JSON-object input |
| `status` | `PENDING`, `RUNNING`, `SUCCEEDED`, or `FAILED` |
| `result`, `error` | JSON objects or null |
| `attempt_ids` | IDs of persisted attempts |
| `attempts_count` | Number of attempts started, initially 0; incremented atomically by each claim |
| `max_attempts` | Total attempt budget saved from `MAX_ATTEMPTS` when the job is created, including the first attempt |
| `available_at` | UTC-aware earliest claim time; a pending job can be waiting for its retry delay |
| `created_at`, `updated_at` | UTC-aware creation and last-update timestamps in ISO 8601 format |

Permission policies and permitted-ID lists are not currently included in job responses.

### Attempt history

`GET /jobs/{job_id}/attempts` uses the same user-token authentication and job read permissions as `GET /jobs/{job_id}`. Missing and inaccessible jobs both return 404, `Job not found`. A permitted worker grant alone does not give that worker's owner user-facing read access.

The response is a JSON array ordered by descending `attempt_number`. Pagination defaults to `limit=50`, `offset=0`; limit must be 1-100 and offset nonnegative. Invalid pagination returns 422. A job without attempts, or an offset beyond its history, returns 200 with `[]`.

| Field | Meaning |
| --- | --- |
| `id`, `job_id`, `worker_id` | Integer attempt, job, and assigned worker IDs |
| `job_type`, `params` | Job type and the attempt's JSON-object input |
| `attempt_number` | Positive execution attempt number within the job |
| `status` | `RUNNING`, `SUCCEEDED`, `FAILED`, or `LOST` |
| `lease_expires_at` | Timezone-aware lease deadline in ISO 8601 format; also returned by claim and heartbeat |
| `result`, `error` | Persisted JSON-object outcome fields, or null when absent |
| `created_at`, `updated_at` | Timezone-aware creation and last-update timestamps in ISO 8601 format |

Running attempts have null result and error; succeeded attempts carry a result, and failed attempts carry an error. `updated_at` records the last update, including a persisted heartbeat renewal, not a dedicated execution-finished timestamp. The separate recovery process marks expired running attempts `LOST` and may schedule a retry; earlier attempts remain in this history. Historical terminal attempts migrated from before leases use `updated_at` as a synthetic lease deadline; see [migration notes](development.md#existing-databases).

### Permission policies

Submission requires `permission_policy`. `permitted_user_ids` and `permitted_worker_ids` default to empty lists; IDs must be positive and refer to existing records. A job's creator can always read it, and that creator's workers can claim it when their supported types match. For other users/workers:

| Job policy | Additional access |
| --- | --- |
| `PRIVATE` | None |
| `PERMITTED_USERS` | Listed users can read; their workers can claim |
| `PERMITTED_WORKERS` | Listed workers can claim; their owners do not automatically gain user-facing read access |
| `PERMITTED_WORKERS_AND_USERS` | Either of the two grant types above applies |
| `ALL` | Any authenticated user can read; any compatible authenticated worker can claim |

Grant lists only apply to their corresponding policy. A worker must also support the job type, and the job must be pending, due, and below its attempt limit to be claimable.

### Submission example

Use a bearer token obtained from login:

```http
POST /jobs/ HTTP/1.1
Authorization: Bearer <access_token>
Idempotency-Key: 52745981-d281-4df5-872a-b15417f5ec23
Content-Type: application/json

{
  "job_type": "send_email",
  "params": {"recipient": "person@example.com", "template": "welcome"},
  "permission_policy": "PRIVATE"
}
```

The [quickstart](quickstart.md) provides executable registration/login and job-submission commands.

## Workers

| Method | Route | Request | Response |
| --- | --- | --- | --- |
| POST | `/workers` | JSON: `name`, `supported_types`, `permission_policy`; optional `permitted_user_ids` | Worker metadata plus `secret_api_key` |
| GET | `/workers` | Optional `owner_username`, `owner_id`, `job_type`, `active`, `created_from`, `created_before`, `limit`, `offset` | Accessible workers, newest ID first |
| GET | `/workers/{worker_id}` | Worker ID | Accessible worker, or 404 |

These routes require a user token. `supported_types` is a nonempty set of strings; each entry follows the job-type rules above. Duplicate types are deduplicated. Permitted-user IDs must exist. Pagination defaults and bounds match job lists; `job_type` filters workers supporting that type.

Omit owner filters for all accessible owners or supply `owner_username` to match an exact, case-sensitive username. The same username rules and compatibility with `owner_id` apply as for jobs. `active=true` or `active=false` filters credential/registration status; omitting it includes both. This does not indicate whether a worker process is online. Creation-time filters use the same inclusive `created_from`, exclusive `created_before`, timezone and range-validation rules as jobs, applied to the worker's creation time. Filters and visibility checks apply before pagination. The frontend exposes these filters in the URL and allows viewing accessible workers owned by other users; worker states do not include `LOST`.

Worker visibility policies are `PRIVATE` (owner only), `PERMITTED_USERS` (owner plus listed users), and `ALL` (all authenticated users). Visibility lets users inspect metadata; it does not reveal the API key or let them claim as that worker. Claims use the worker owner's job permissions plus explicit worker grants.

Worker metadata contains `id`, `name`, `active`, `user_id`, `owner_username`, `permission_policy`, `supported_types`, and `permitted_user_ids`. The raw API key is returned only by creation; store it for the independent worker. Reads/lists omit it, and PostgreSQL stores its SHA-256 hash. Worker names are globally unique.

### Job-type suggestions

`GET /job-types?query=add&limit=10` requires a user bearer token and returns a JSON array of distinct supported type names from workers the caller can view, for example `["add_numbers"]`. It reuses worker metadata visibility: owned workers, workers visible to all users, and workers granting the caller visibility. Types declared only by hidden workers are excluded before limiting the results.

The optional `query` is a case-insensitive, literal substring (1–100 characters); `%` and `_` are not wildcards. Omit it to request suggestions without a search term. Names retain their stored spelling and whitespace, are deduplicated by exact name, and are ordered by ascending name. `limit` defaults to 10 and must be 1–100. No matches returns 200 with `[]`; invalid parameters return 422.

The source is worker registrations, including visible inactive registrations, rather than a separate job-type catalog. Suggestions do not establish that a worker is online or eligible to claim a submitted job. They do not restrict the existing submission or worker-registration contracts.

### Worker workflow

Create a worker with a user token:

```http
POST /workers HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{"name":"email-worker","supported_types":["send_email"],"permission_policy":"PRIVATE"}
```

Then claim with the returned API key:

```http
POST /workers/claim HTTP/1.1
X-API-Key: <worker-api-key>
```

Claim takes **no request body**. Job types come from the worker's stored capabilities; any supplied body, including the former `supported_types` field, is ignored. An empty compatible accessible queue returns **404**, `{"detail":"No jobs were found"}`. A worker with no stored types cannot claim work.

A successful claim returns `id` (the attempt ID), `job_id`, `job_type`, `attempt_number` (1 for the first execution, increasing on retries), `status` (`RUNNING`), `params`, and `lease_expires_at`. PostgreSQL `FOR UPDATE SKIP LOCKED` selects the oldest eligible job by ID, requiring `available_at <= database_now` and `attempts_count < max_attempts`. Under the job lock, claim increments `attempts_count` and uses that value for the new attempt number. The initial deadline is database time plus `LEASE_SECONDS` (example configuration: 120 seconds). The counter, job status, and attempt insert commit in one transaction before the response. An empty result can also mean jobs are waiting for their scheduled time or eligible rows are temporarily locked by other claims.

The worker executes outside Orqbit, then sends one outcome:

| Method | Route | JSON body | Response |
| --- | --- | --- | --- |
| POST | `/workers/{attempt_id}/succeed` | `{"result":{"message_id":"example-message-id"}}` | `{"Status":"200 OK"}` |
| POST | `/workers/{attempt_id}/fail` | `{"error":{"code":"DELIVERY_FAILED","message":"Provider failure"}}` | `{"Status":"200 OK"}` |

Both routes require the owning worker's API key. Use the returned attempt ID, not the job ID. Result/error must be JSON objects. The attempt is locked and checked for ownership. A first outcome requires the current `RUNNING` attempt of a running job, a matching attempt number/count, and an unexpired lease; it updates the attempt together with its job. Repeating the accepted outcome with the same payload returns 200, `{"Status":"200 OK"}`, even after the recorded lease deadline, without changing stored values or timestamps. JSON object key order does not affect matching, and equivalent numeric representations such as `1` and `1.0` match; array order and boolean versus numeric values do affect matching. Changed payloads, contradictory outcomes, and reports against lost attempts return 409. No extra idempotency header is required. A worker-reported failure remains terminal, even when the job has unused attempts. Recovery and retries are performed by the separate process described below.

### Attempt heartbeats and leases

While executing, the owning worker can renew its attempt with a bodyless request:

```http
POST /workers/{attempt_id}/heartbeat HTTP/1.1
X-API-Key: <worker-api-key>
```

A successful heartbeat returns HTTP 200 with the persisted deadline, for example:

```json
{"lease_expires_at":"2026-11-11T15:20:00Z"}
```

The request must target an owned `RUNNING` attempt whose lease has not expired. The server locks the attempt, then reads PostgreSQL `clock_timestamp()` to check expiry and calculate renewal within the same transaction. Success/failure checks use the same locking and database-time rule. A lease is expired when database time is greater than or equal to `lease_expires_at`.

Renewal sets the deadline to `max(existing_deadline, database_now + LEASE_EXTENSION_SECONDS)`. The example configuration uses a 60-second renewal window. This gives time from the heartbeat's processing time; it does not add 60 seconds to the previous deadline. An early heartbeat cannot shorten an existing lease. Choose a heartbeat interval with enough margin below the renewal window for requests and processing delays. Use the deadline returned by each successful response. An expired lease cannot be revived by retrying a heartbeat.

This is a per-attempt heartbeat, not a separate worker-process liveness signal. It renews only the addressed attempt. The [add_numbers worker](../examples/workers/add_numbers/README.md) and [delay worker](../examples/workers/delay/README.md) do not send heartbeats. The [delay_with_heartbeat worker](../examples/workers/delay_with_heartbeat/README.md) demonstrates execution beyond the initial lease and stops without reporting an outcome when ownership cannot be confirmed.

Expiry immediately blocks new outcomes and renewals. Persisted states change when the separate recovery process scans the expired attempt. Workers should stop work cooperatively after losing their lease; lease validation cannot undo external side effects already performed. Hard execution deadlines are not implemented, so successful heartbeats can keep a running attempt leased indefinitely.

### Recovery and bounded retries

Run `python -m recovery` with `backend/src` on the Python import path, or start the Compose `recovery` service. Each scan processes at most `RECOVERY_BATCH_SIZE` expired running attempts (default 1000), then pauses for `RECOVERY_INTERVAL_SECONDS` (default 5). Recovery must be running for persisted expiry handling and retry scheduling; API readiness does not check it.

Only lease expiry is retried automatically. A scan closes the old attempt as `LOST`. If its number matches the job's `attempts_count` and budget remains, recovery changes the running job to `PENDING` and sets `available_at` in the same transaction. Otherwise, a current attempt that exhausted the budget leaves the job `FAILED` with `error={"code":"attempts_exhausted","message":"Maximum attempts reached after lease expiry"}`. There is no retry of a reported `/fail` outcome and no manual retry endpoint.

`MAX_ATTEMPTS` is an integer from 1 to 5, defaulting to 1. It includes the first execution, so 1 disables retries and 3 allows up to two retries. It is application configuration, not a job-submission field. Each job saves this limit at creation; configuration changes and matching submission replays do not reset an existing budget.

After lost attempt number `n`, the fixed backoff is `min(10 * 2**(n - 1), 60)` seconds: 10, 20, 40, then 60 seconds. Recovery adds it to its database-time scan cutoff and persists `available_at`. This is the earliest claim time, not a promised execution time; scan delays, database contention, worker availability, and polling can delay execution. There is no jitter or configurable backoff policy in this version.

Recovery does not create the next attempt. A later compatible, permitted worker claims it with a new attempt ID and the next number. Earlier attempts retain their ownership, parameters, timestamps, and outcomes. A late success/failure for a lost attempt returns 409 and its heartbeat returns 400, even when that worker owns the new attempt. Fresh reports before recovery still fail with 400 once the lease has expired. Exact replays of accepted outcomes remain unchanged and do not schedule work.

An expired lease does not prove that the old worker stopped. Retried work can repeat external effects, so workers should deduplicate them using a stable job or business-operation key across attempts. Submission keys and attempt fencing do not provide exactly-once execution.

## Errors

Errors use a top-level `detail` field. Request validation returns an array containing field `type`, `loc`, and `msg`; rejected input values are omitted. Other errors use string details.

| Condition | Status and detail |
| --- | --- |
| Missing/invalid user token | 401; missing credentials use `Not authenticated`, invalid tokens use `Could not validate credentials` |
| Login with wrong credentials or inactive user | 401, `Incorrect username or password` |
| Inactive user on a user-protected route | 403, `Inactive user` |
| Missing/invalid API key or inactive worker | 401, `Could not validate credentials` |
| Missing/inaccessible job | 404, `Job not found` |
| Missing/inaccessible worker | 404, `Worker not found` |
| Empty claim result | 404, `No jobs were found` |
| Missing attempt or another worker's attempt | 404, `Attempt not found` |
| Expired lease on a running attempt, for heartbeat or a first outcome | 400, `The lease has expired` |
| Heartbeat against a terminal attempt | 400, `The attempt is not running` |
| Changed or contradictory outcome, or report against a lost attempt | 409, `Conflicting outcome report` |
| Duplicate username/email | 400, `User with username ... already exists` or `User with email ... already exists` |
| Duplicate worker name | 409, `Worker name already exists` |
| Nonexistent permission IDs | 422, `Some permitted users do not exist` or `Some permitted workers do not exist` |
| Invalid fields or malformed body | 422, validation detail array |
| PostgreSQL data error, including oversized integer IDs or null characters in JSON strings | 422, `Input contains a value PostgreSQL cannot store` |

Exact replays of accepted outcomes return 200; conflicting reports return 409. Idempotency keys apply to job submission only. PostgreSQL data errors are mapped to a generic response without SQL/exception details; other storage/application failures may still return 500.

## Health behavior

`GET /health/live` and its alias `GET /health` return 200 with `{"status":"ok"}` while the API responds, including during a database outage.

`GET /health/ready` opens a fresh connection, compares database Alembic heads to shipped migration scripts, and runs zero-row queries selecting every mapped column in each application table. It returns 200 with `{"status":"ready"}` or 503 with `{"status":"not_ready"}`. Both responses carry `Cache-Control: no-store`. Missing tables/columns, migration mismatches, unavailable PostgreSQL, and query failures cause 503 without exposing database details.

Probes are read-only, use a three-second connection timeout and a two-second timeout per SQL statement, and avoid waiting for an application pool slot. They never run migrations and do not audit indexes or constraints. Application connections are checked before reuse so they can reconnect after a PostgreSQL restart. Every readiness request checks again; database reconnection is distinct from abandoned-job recovery.

## Proposed versioned contract

The versioned routes and additional semantics below are **not implemented**. Build on the existing authentication and attempt model when deciding whether to introduce this contract. It is a design proposal, not the current API.

| Method | Proposed route | Purpose |
| --- | --- | --- |
| POST | `/v1/jobs` | Authenticated submission with required `Idempotency-Key`; return 201 and `Location` |
| GET | `/v1/jobs` | Creator-scoped, cursor-paginated listing with status/type filters |
| GET | `/v1/jobs/{job_id}` | Authorized status/result lookup |
| GET | `/v1/jobs/{job_id}/attempts` | Authorized, paginated execution history with secrets redacted |
| POST | `/v1/workers/register` | Bind a process-instance ID to an authenticated worker principal |
| POST | `/v1/workers/me/heartbeat` | Record worker process liveness |
| POST | `/v1/workers/claim` | Claim one due job from permitted types; return job, attempt ID, token, and lease metadata |
| POST | `/v1/jobs/{job_id}/attempts/{attempt_id}/heartbeat` | Renew that attempt's lease using its token |
| POST | `/v1/jobs/{job_id}/attempts/{attempt_id}/succeed` | Idempotently acknowledge success for the current owned attempt |
| POST | `/v1/jobs/{job_id}/attempts/{attempt_id}/fail` | Record structured failure and apply the retry policy |

Worker credentials authenticate the principal; requested types are intersected with its permitted capabilities. Registration and a user-supplied worker name do not themselves establish identity. Use separate transport credentials for clients and workers, and send attempt tokens through a documented protected header.

Proposed response rules:

- Empty claim: 204 without a JSON body. Workers poll with bounded backoff and jitter.
- Invalid/missing credentials: 401; insufficient permission: 403. Creator-facing lookup may use 404 to conceal inaccessible jobs consistently.
- Missing required idempotency key: 400. Same key with changed content: 409. An identical replay returns the original 201 creation response and job identity.
- Unknown job/attempt: 404. Stale lease, wrong attempt generation, or contradictory terminal acknowledgement: 409.
- Exact repeat of an accepted terminal acknowledgement: 200 with the same acknowledgement body; no new attempt or transition.
- Invalid fields: 422. Oversized body: 413. Rate/queue quota limit: 429 with retry guidance. Temporary storage unavailability: 503.

Define one structured error envelope, request IDs, UTC timestamp format, payload/result limits, cursor behavior, and credential/token headers in the stable OpenAPI contract. Keep worker tokens out of job reads and history. Breaking changes to current routes should be introduced through versioning or an explicitly documented prototype migration.
