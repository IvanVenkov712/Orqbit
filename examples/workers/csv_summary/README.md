# CSV summary worker

Reads CSV text from `params.csv` and computes statistics for the numeric columns selected by `params.columns`. CSV data and results travel through Orqbit's JSON API; no filesystem access or external storage is required.

## Setup and run

Start Orqbit and authenticate using the [quickstart](../../../docs/quickstart.md). Register a worker with your user bearer token using `POST /workers`:

```json
{"name":"csv-summary","supported_types":["csv_summary"],"permission_policy":"PRIVATE"}
```

From this directory, with Python 3.13 and uv installed:

```powershell
uv sync --locked
Copy-Item .env.example .env
```

Set `API_KEY` to the returned `secret_api_key` and adjust `API_URL`. The adjacent `.env` is read regardless of working directory; environment variables override it. Keep the real `.env` private.

| Setting | Default | Meaning |
| --- | --- | --- |
| `API_KEY` | Required | Registered worker's secret API key |
| `API_URL` | Required | API base URL; example uses `http://127.0.0.1:8000` |
| `POLL_INTERVAL` | 2 | Seconds between empty-queue polls |
| `REQUEST_TIMEOUT` | 10 | HTTP timeout in seconds |

Polling and HTTP timeout must be positive and finite.

```powershell
uv run --locked python worker.py
```

Using the same user, submit `POST /jobs/` with a fresh `Idempotency-Key`:

```json
{
  "job_type": "csv_summary",
  "params": {
    "csv": "name,amount,units\nA,10,2\nB,20,4\n",
    "columns": ["amount", "units"]
  },
  "permission_policy": "PRIVATE"
}
```

Read `GET /jobs/{id}` for `SUCCEEDED` and this result:

```json
{
  "row_count": 2,
  "columns": {
    "amount": {"count": 2, "sum": 30.0, "min": 10.0, "max": 20.0, "mean": 15.0},
    "units": {"count": 2, "sum": 6.0, "min": 2.0, "max": 4.0, "mean": 3.0}
  }
}
```

Register this worker for `csv_summary` only.

## Input rules and limits

- CSV uses commas and a header with unique, nonempty names. Column names are matched exactly.
- `columns` is a nonempty list of unique names present in that header.
- Quoted commas, quoted newlines, and CRLF line endings are supported. Blank lines after the header are skipped.
- Every nonblank record must have the same number of fields as the header.
- Selected cells must contain finite numbers; blank cells, text, NaN, infinity, and overflowing sums are rejected. Unselected columns may contain text.
- `row_count` excludes the header and blank lines. A header-only file returns zero counts and sums, with null minimum, maximum, and mean.
- Statistics use Python floating-point arithmetic. The CSV text is already loaded as a JSON string; records are then read incrementally. This example is intended for small inputs.

Invalid input is reported as a failed attempt with `INVALID_PARAMS`. The worker sends no heartbeats, so processing and outcome reporting must finish within the initial lease. HTTP/connection errors stop it with exit code 1, without retrying or sending a second outcome. Ctrl+C stops the worker; there is no worker-side crash recovery.

## Code and checks

- `summary.py`: CSV validation and numeric aggregation.
- `execution.py`: input failures and successful outcome reporting.
- `worker.py`: claim loop, startup, and process-level errors.
- `settings.py` and `api.py`: configuration and authenticated HTTP.
- `tests/`: separate files for CSV behavior, execution, HTTP, settings, and polling.

Each worker is independently installable using only its own directory. It imports neither backend nor sibling-worker code. Tests use mocked HTTP and require no running API or PostgreSQL.

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```
