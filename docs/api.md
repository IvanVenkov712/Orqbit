# API reference and proposed changes

## Existing prototype routes

These routes come from `src/api/routers/`. Job routes use user bearer tokens; worker claims and outcome reports use an `X-API-Key` and enforce worker ownership. There is no version prefix or idempotency-key handling. All successful routes currently return HTTP 200, including creation. Request validation uses FastAPI/Pydantic; invalid bodies normally return 422.

| Method | Route | Request body | Successful response |
| --- | --- | --- | --- |
| POST | `/jobs/` | `job_type: string`, `params: object` | Job object |
| GET | `/jobs` | None | Array of all jobs, ordered by ID |
| GET | `/jobs/{job_id}` | None | Job object |
| POST | `/workers/claim` | None | Attempt for the oldest accessible pending job matching the authenticated worker's stored types |
| POST | `/workers/{attempt_id}/succeed` | `result: object` | `{"Status":"200 OK"}` |
| POST | `/workers/{attempt_id}/fail` | `error: object` | `{"Status":"200 OK"}` |
| GET | `/health/live` | None | `{"status":"ok"}` |
| GET | `/health` | None | Liveness alias: `{"status":"ok"}` |
| GET | `/health/ready` | None | `{"status":"ready"}` when the database/schema is usable |

Existing IDs are integers. The ID in `/workers/{attempt_id}/...` identifies an **attempt**, as returned by claiming.

A job response contains `id`, `job_type`, `params`, `status`, `result`, and `error`; the latter two can be null. Status values are `PENDING`, `RUNNING`, `SUCCEEDED`, and `FAILED`.

### Health behavior

Liveness checks only that the API responds. It keeps returning 200 during a database outage or when migrations have not been applied. `/health` remains a compatible alias for `/health/live`.

Readiness opens a fresh PostgreSQL connection, compares the database's Alembic heads to the migration scripts shipped with the application, then runs a zero-row query selecting every required job column. An empty or outdated migration stamp, a missing table/column, inaccessible database, or failed query produces **503** with `{"status":"not_ready"}`. It does not return SQL, exception details, or credentials. Both readiness outcomes use `Cache-Control: no-store`.

Probes run read-only, with a three-second connection timeout and a two-second timeout per SQL statement, using a separate connection rather than waiting for an application pool slot. They never create or migrate tables. The revision check plus column query verifies the schema needed for job reads; it is not a full audit of every possible manual schema change. API connections check pooled connections before reuse so they can reconnect after PostgreSQL restarts. Readiness is checked again on every request.

### Example interaction

Submit using `POST /jobs/`:

```json
{
  "job_type": "send_email",
  "params": {"recipient": "person@example.com", "template": "welcome"}
}
```

Claim using `POST /workers/claim` with the worker's API key and no request body:

```http
POST /workers/claim HTTP/1.1
X-API-Key: <worker-api-key>
```

Job types come from the worker's registered `supported_types` in the database.
The former `ClaimJob` body is no longer part of the contract; any supplied body
is ignored, including its `supported_types`. Workers with no stored types cannot
claim jobs. The response identifies the claimed attempt in `id` and its job in
`job_id`.

With the returned attempt ID, report success using `POST /workers/1/succeed`:

```json
{"result": {"message_id": "example-message-id"}}
```

Alternatively, report failure for a running job using `POST /workers/1/fail`:

```json
{"error": {"code": "DELIVERY_FAILED", "message": "Temporary provider failure"}}
```

Use the actual returned ID instead of `1`. Success and failure are alternative outcomes. A reported failure does not currently schedule a retry, even if its message says the problem was temporary.

### Existing error behavior

| Condition | Response |
| --- | --- |
| Read/update references an absent job | 404, `{"detail": "Job not found"}` |
| Claim finds no matching pending job | 404, `{"detail": "No jobs were found"}` |
| Success/failure references a job that is not running | 400, `{"detail": "Job not running"}` |

Readiness has the database-outage behavior described above; job endpoints do not yet have a general database-outage error mapping. Repeating an accepted success/failure report currently returns 400 because the job is no longer running.

## Proposed versioned contract

The following endpoints and semantics are **not implemented**. Finalize them alongside the identity and attempt model before exposing a stable client API.

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
