# API reference and proposed changes

## Existing prototype routes

These routes come from `src/api/routers/`. They have no authentication, version prefix, ownership enforcement, or idempotency-key handling. All successful routes currently return HTTP 200, including creation. Request validation uses FastAPI/Pydantic; invalid bodies normally return 422.

| Method | Route | Request body | Successful response |
| --- | --- | --- | --- |
| POST | `/jobs/` | `job_type: string`, `params: object` | Job object |
| GET | `/jobs` | None | Array of all jobs, ordered by ID |
| GET | `/jobs/{job_id}` | None | Job object |
| POST | `/workers/claim` | `supported_types: string[]` | Oldest matching pending job by ID |
| POST | `/workers/{job_id}/succeed` | `result: object` | `{}` |
| POST | `/workers/{job_id}/fail` | `error: object` | `{}` |

Existing IDs are integers. The ID in `/workers/{job_id}/...` identifies a **job**, despite the route prefix.

A job response contains `id`, `job_type`, `params`, `status`, `result`, and `error`; the latter two can be null. Typical status values are `PENDING`, `RUNNING`, `SUCCEEDED`, and `FAILED`. The model also contains an unintended lowercase `pending` value; see [known problems](status.md).

### Example interaction

Submit using `POST /jobs/`:

```json
{
  "job_type": "send_email",
  "params": {"recipient": "person@example.com", "template": "welcome"}
}
```

Claim using `POST /workers/claim`:

```json
{"supported_types": ["send_email"]}
```

With the returned job ID, report success using `POST /workers/1/succeed`:

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

No explicit response behavior is defined for database outages. Repeating an accepted success/failure report currently returns 400 because the job is no longer running.

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
| GET | `/health/live` | Process liveness |
| GET | `/health/ready` | Database/schema readiness |

Worker credentials authenticate the principal; requested types are intersected with its permitted capabilities. Registration and a user-supplied worker name do not themselves establish identity. Use separate transport credentials for clients and workers, and send attempt tokens through a documented protected header.

Proposed response rules:

- Empty claim: 204 without a JSON body. Workers poll with bounded backoff and jitter.
- Invalid/missing credentials: 401; insufficient permission: 403. Creator-facing lookup may use 404 to conceal inaccessible jobs consistently.
- Missing required idempotency key: 400. Same key with changed content: 409. An identical replay returns the original 201 creation response and job identity.
- Unknown job/attempt: 404. Stale lease, wrong attempt generation, or contradictory terminal acknowledgement: 409.
- Exact repeat of an accepted terminal acknowledgement: 200 with the same acknowledgement body; no new attempt or transition.
- Invalid fields: 422. Oversized body: 413. Rate/queue quota limit: 429 with retry guidance. Temporary storage unavailability: 503.

Define one structured error envelope, request IDs, UTC timestamp format, payload/result limits, cursor behavior, and credential/token headers in the stable OpenAPI contract. Keep worker tokens out of job reads and history. Breaking changes to current routes should be introduced through versioning or an explicitly documented prototype migration.
