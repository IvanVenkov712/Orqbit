# Docker and PowerShell quickstart

Use PowerShell, Git, and a running Docker engine in Linux-container mode. Docker Compose must support `up --wait`. No host Python environment or PostgreSQL installation is required. Run these steps in one PowerShell session so the login token and job ID remain available.

## 1. Configure the stack

For a new checkout:

```powershell
git clone https://github.com/IvanVenkov712/Orqbit.git Orqbit-demo
Set-Location Orqbit-demo
Copy-Item .env.compose.example .env.compose
```

If using an existing checkout, work in its root and retain any existing `.env.compose` settings. Shell environment variables override `--env-file`; use a fresh shell without exported Orqbit settings if you want the file to control configuration.

Edit `.env.compose`: choose a local database password and put it in both `POSTGRES_PASSWORD` and `DATABASE_URL`. Keep the URL hostname as `db` and match the user/database names. URL-encode reserved characters in the URL password.

Generate a signing key using PowerShell:

```powershell
$keyBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($keyBytes)
$rng.Dispose()
-join ($keyBytes | ForEach-Object { $_.ToString("x2") })
```

Replace `SECRET_KEY=replace_with_secret_key` in `.env.compose` with that output. It must be 64 lowercase hexadecimal characters. Keep `ALGORITHM=HS256` and a positive `ACCESS_TOKEN_EXPIRE_MINUTES` (the example uses 30). Keep positive `LEASE_SECONDS=120` for the initial attempt lease and `LEASE_EXTENSION_SECONDS=60` for the heartbeat renewal window. In existing files, rename `PROTRACTION_SECONDS` to `LEASE_EXTENSION_SECONDS`; Compose no longer reads the old name. See the [lease protocol](api.md#attempt-heartbeats-and-leases) for expiry and renewal behavior. The real environment file is ignored by Git and excluded from the image.

Keep `MAX_ATTEMPTS=1` for this walkthrough, including its terminal-failure demonstration in step 6. To enable retries for new jobs, set it to an integer from 2 to 5 (for example, `MAX_ATTEMPTS=3` allows the first execution plus two retries) and run the startup command below again to recreate the API and recovery services with that setting. Existing jobs retain their saved limit. Only lost attempts are retried; a worker-reported failure remains terminal. See [recovery and bounded retries](api.md#recovery-and-bounded-retries) for scheduling and ownership rules.

Set the URL to match `API_PORT` in the file, then validate Compose interpolation:

```powershell
$api = "http://127.0.0.1:8000"
docker compose --env-file .env.compose config --quiet
```

`config --quiet` checks Compose configuration, not application settings such as the signing-key format.

## 2. Build, migrate, and start

```powershell
docker compose --env-file .env.compose up --build --wait --wait-timeout 120 api recovery
docker compose --env-file .env.compose ps --all
Invoke-RestMethod -Uri "$api/health/live"
Invoke-RestMethod -Uri "$api/health/ready"
```

Compose waits for PostgreSQL, runs the one-shot Alembic migration service, and starts the API and the separate recovery process when migrations succeed. Both reuse the backend image and settings. A successful migration container exits with code 0. Expect liveness `{"status":"ok"}` and readiness `{"status":"ready"}`. Readiness checks database access, migration heads, and every mapped table/column; it does not check the recovery process.

Recovery runs `python -m recovery`, scanning up to `RECOVERY_BATCH_SIZE` expired running attempts per transaction and pausing `RECOVERY_INTERVAL_SECONDS` between scans (defaults: 1000 and 5 seconds). An expired attempt becomes `LOST`; its job becomes `PENDING` with a delayed `available_at` when budget remains, or `FAILED` with an `attempts_exhausted` error when the limit is reached. Both changes commit together. The service restarts automatically unless explicitly stopped. Include `recovery` when selecting services explicitly; an unqualified `docker compose --env-file .env.compose up --build --wait` includes it along with the frontend.

If startup fails:

```powershell
docker compose --env-file .env.compose logs db migrate api recovery
```

An existing database with legacy jobs may need preparation before migration; see [migration notes](development.md#existing-databases).

## 3. Register and log in

Choose a password containing 6?20 characters, using only ASCII letters, digits, and `@`, `$`, `#`, `%`. Include at least one uppercase letter, lowercase letter, digit, and one of those symbols.

```powershell
$password = Read-Host "Choose a demo password matching the rules above"
$registration = @{
    username = "demo-user"
    email = "demo@example.com"
    full_name = "Demo user"
    password = $password
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$api/auth/register" -ContentType application/json -Body $registration

$login = @{ username = "demo-user"; password = $password }
$token = Invoke-RestMethod -Method Post -Uri "$api/auth/login" -ContentType application/x-www-form-urlencoded -Body $login
$headers = @{ Authorization = "Bearer $($token.access_token)" }
```

Registration is needed once per database. If the account already exists, log in with its original password. Login uses form data; registration uses JSON. Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES`; repeat the login commands if necessary.

## 4. Create and read a private job

```powershell
$submissionHeaders = @{
    Authorization = $headers.Authorization
    "Idempotency-Key" = [guid]::NewGuid().ToString()
}
$job = Invoke-RestMethod -Method Post -Uri "$api/jobs/" -Headers $submissionHeaders -ContentType application/json -Body '{"job_type":"example","params":{"hello":"world","values":[true,null,3]},"permission_policy":"PRIVATE"}'
$before = Invoke-RestMethod -Uri "$api/jobs/$($job.id)" -Headers $headers
$expected = $before | ConvertTo-Json -Depth 20 -Compress
$before
```

The response includes the job ID, authenticated `user_id`, submitted parameters, `PENDING` status, null result/error, and empty `attempt_ids`. Reuse `$submissionHeaders` with the same body to retry this submission; generate a new key for a new job. Reusing a key with changed content returns 409. No worker executes it in this demonstration. To register a worker and exercise claiming/reporting, see the [API workflow](api.md#worker-workflow).

## 5. Recreate containers and verify persistence

```powershell
docker compose --env-file .env.compose down
docker compose --env-file .env.compose up --wait --wait-timeout 120 api recovery
Invoke-RestMethod -Uri "$api/health/ready"
$after = Invoke-RestMethod -Uri "$api/jobs/$($job.id)" -Headers $headers
if (($after | ConvertTo-Json -Depth 20 -Compress) -ne $expected) {
    throw "The saved job changed across container recreation"
}
Write-Output "Job $($after.id) survived container recreation."
```

The volume preserves both the user and job. Keep the same signing key so unexpired tokens remain valid, or log in again after recreation. For an explicit migration rerun:

```powershell
docker compose --env-file .env.compose run --rm migrate
```

## 6. Verify an abandoned attempt

Using the authenticated session and the still-pending `example` job above, register a worker and claim once without sending a heartbeat or outcome. This simulates a worker that stops immediately after claim. This demonstration requires that the job was created with `max_attempts=1`; otherwise it becomes pending for a retry instead of reaching terminal failure after the first lost attempt:

```powershell
$worker = Invoke-RestMethod -Method Post -Uri "$api/workers" -Headers $headers -ContentType application/json -Body '{"name":"recovery-demo","supported_types":["example"],"permission_policy":"PRIVATE"}'
$workerHeaders = @{ "X-API-Key" = $worker.secret_api_key }
$attempt = Invoke-RestMethod -Method Post -Uri "$api/workers/claim" -Headers $workerHeaders
$deadline = (Get-Date).AddSeconds(180)
do {
    $recovered = Invoke-RestMethod -Uri "$api/jobs/$($attempt.job_id)" -Headers $headers
    if ($recovered.status -eq "FAILED") { break }
    if ((Get-Date) -ge $deadline) { throw "Job did not reach FAILED within 180 seconds" }
    Start-Sleep -Seconds 1
} while ($true)
$history = Invoke-RestMethod -Uri "$api/jobs/$($attempt.job_id)/attempts" -Headers $headers
if ($history[0].id -ne $attempt.id -or $history[0].status -ne "LOST") {
    throw "The abandoned attempt was not marked LOST"
}
$recovered
$history
```

The 180-second bound assumes the default 120-second initial lease, 5-second scan interval, and no backlog. Increase it if you configured longer intervals. The job is `FAILED`, the attempt is `LOST`, and late success/failure reports for that attempt return 409. Reuse an existing worker's API key if its name is already registered.

## 7. Stop

```powershell
docker compose --env-file .env.compose down
```

Ordinary `down` retains the named database volume. Adding `--volumes` deletes that volume and its data. Use the same checkout directory and Compose project name to keep selecting the same volume. Changing credentials in `.env.compose` does not change credentials already initialized inside an existing PostgreSQL volume.

## Automated verification

Run `python backend/tests/compose_smoke.py` from the repository root to create a separate generated Compose project, register/log in a user, and test authenticated job persistence, migrations, database outage/reconnection, abandoned-attempt recovery, late-outcome rejection, and container recreation. The check uses a 5-second lease and 1-second recovery interval, supplies its own signing key and credentials, and removes its own containers/volume afterward. It requires host Python and Docker, but no `.env.compose` file. See [testing](testing.md) for commands and [status](status.md#verification-performed) for earlier recorded results.
