# Clean-checkout demonstration

These commands use PowerShell, Git, and a running Docker engine in Linux-container mode. Docker Compose must support `up --wait`. No host Python environment, PostgreSQL installation, or dependency installation is required.

## 1. Get the source and configure local credentials

Start in a fresh PowerShell window without exported Orqbit database variables. Shell environment variables take precedence over `--env-file`.

```powershell
git clone https://github.com/IvanVenkov712/Orqbit.git Orqbit-demo
Set-Location Orqbit-demo
Copy-Item .env.compose.example .env.compose
```

Edit `.env.compose` before starting. Choose a local password, updating both `POSTGRES_PASSWORD` and the password in `DATABASE_URL`. Keep the database hostname as `db`, not `localhost`, and ensure the user/database values match. URL-encode reserved characters in the URL password. These credentials are for this local development stack; production credentials must be supplied separately. The real environment file is ignored by Git and excluded from the image.

The API defaults to port 8000. If it is occupied, change `API_PORT` in `.env.compose` and use that port below:

```powershell
$api = "http://127.0.0.1:8000"
docker compose --env-file .env.compose config --quiet
```

## 2. Build, migrate, and start

```powershell
docker compose --env-file .env.compose build
docker compose --env-file .env.compose up --wait --wait-timeout 120 db
docker compose --env-file .env.compose run --rm migrate
docker compose --env-file .env.compose up --wait --wait-timeout 120 api
docker compose --env-file .env.compose ps --all
Invoke-RestMethod -Uri "$api/health/live"
Invoke-RestMethod -Uri "$api/health/ready"
```

Expect liveness `{"status":"ok"}` and readiness `{"status":"ready"}`. `up --wait ... api` waits for the API's readiness health check, not only for its process to start. Readiness checks PostgreSQL, the Alembic revision, and the required job table columns.

The separate `migrate` service runs `alembic upgrade head`. Starting the API also runs its migration dependency, so an already applied migration is checked again without modifying existing jobs. A successful one-shot migration container exits with code 0. On a migration failure, the API is not started. Diagnose startup with:

```powershell
docker compose --env-file .env.compose logs db migrate api
```

For later starts, the shorter equivalent is `docker compose --env-file .env.compose up --build --wait --wait-timeout 120 api`.

## 3. Create and read a job

Keep using the same PowerShell window so the job ID and expected response remain available:

```powershell
$job = Invoke-RestMethod -Method Post -Uri "$api/jobs/" -ContentType application/json -Body '{"job_type":"example","params":{"hello":"world","values":[true,null,3]}}'
$before = Invoke-RestMethod -Uri "$api/jobs/$($job.id)"
$expected = $before | ConvertTo-Json -Depth 20 -Compress
$before
```

Expect the returned job ID, the submitted parameters, and status `PENDING`. No worker is included, so the job stays pending during this demonstration.

## 4. Recreate containers and verify persistence

```powershell
docker compose --env-file .env.compose down
docker compose --env-file .env.compose up --wait --wait-timeout 120 api
Invoke-RestMethod -Uri "$api/health/ready"
$after = Invoke-RestMethod -Uri "$api/jobs/$($job.id)"
if (($after | ConvertTo-Json -Depth 20 -Compress) -ne $expected) {
    throw "The saved job changed across container recreation"
}
Write-Output "Job $($after.id) survived container recreation."
```

Both reads should return the same job. The named PostgreSQL volume survives the `down` command even though the containers are deleted.

## 5. Stop

```powershell
docker compose --env-file .env.compose down
```

Your jobs remain in the volume for the next start. Adding `--volumes` to this command **deletes the database volume and every stored job**. Changing the Compose project name or using another checkout directory selects a different project volume by default; continue using the same directory to keep using this database.

## Automated verification

The separate `python tests/compose_smoke.py` check is configured in CI. It creates a private Compose project with generated credentials, checks readiness and liveness, tests an actual database outage and recovery, and verifies job persistence after container recreation. It removes only that test project's containers and volume afterward. This automated check requires Python, while the manual Docker workflow above does not.
