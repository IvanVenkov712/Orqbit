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

Set the URL to match `API_PORT` in the file, then validate Compose interpolation:

```powershell
$api = "http://127.0.0.1:8000"
docker compose --env-file .env.compose config --quiet
```

`config --quiet` checks Compose configuration, not application settings such as the signing-key format.

## 2. Build, migrate, and start

```powershell
docker compose --env-file .env.compose up --build --wait --wait-timeout 120 api
docker compose --env-file .env.compose ps --all
Invoke-RestMethod -Uri "$api/health/live"
Invoke-RestMethod -Uri "$api/health/ready"
```

Compose waits for PostgreSQL, runs the one-shot Alembic migration service, and starts the API when migrations succeed. A successful migration container exits with code 0. Expect liveness `{"status":"ok"}` and readiness `{"status":"ready"}`. Readiness checks database access, migration heads, and every mapped table/column.

If startup fails:

```powershell
docker compose --env-file .env.compose logs db migrate api
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
docker compose --env-file .env.compose up --wait --wait-timeout 120 api
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

## 6. Stop

```powershell
docker compose --env-file .env.compose down
```

Ordinary `down` retains the named database volume. Adding `--volumes` deletes that volume and its data. Use the same checkout directory and Compose project name to keep selecting the same volume. Changing credentials in `.env.compose` does not change credentials already initialized inside an existing PostgreSQL volume.

## Automated verification

Run `python backend/tests/compose_smoke.py` from the repository root to create a separate generated Compose project, register/log in a user, and test authenticated job persistence, migrations, database outage/reconnection, and container recreation. It supplies its own signing key and credentials and removes its own containers/volume afterward. It requires host Python and Docker, but no `.env.compose` file. See [testing](testing.md) for commands and [status](status.md#verification-performed) for recorded results; the revised manual commands have not been re-executed end to end against Docker during this documentation refresh.
