# 8. Everyday use and troubleshooting

[← Create your own worker](07-create-your-own-worker.md) · [Tutorial home](README.md)

## Stop and come back later

Let active jobs finish if possible, then press **Ctrl+C** in each worker terminal. From a terminal at the **repository root**, stop Orqbit:

```powershell
docker compose --env-file .env.compose down
```

Your accounts, registrations, jobs, and results remain in Docker's database volume. **Do not add `--volumes`** if you want to keep them: that option deletes the stored data.

Next time, open Docker Desktop and run from the same repository root:

```powershell
docker compose --env-file .env.compose up --build --wait --wait-timeout 120 frontend recovery
```

Open [http://localhost:8080](http://localhost:8080) and sign in with your existing account. In another terminal, start your existing worker again:

```powershell
cd examples/workers/add_numbers
uv run --locked python worker.py
```

Keep the same `.env.compose`, worker `.env`, checkout folder, and Compose project name. You do not need to register accounts or workers again. Changing the database password in the file later does not change the password inside an existing database volume.

## A job stays Pending

Check these in order:

1. **Is the worker program running?** Its terminal should remain open without a returned command prompt. Active status in the interface only describes its registration.
2. **Does the type match exactly?** `add_numbers` must appear both in the worker's supported types and the submitted job. Capital letters, spaces, and hyphens change the type.
3. **Does its key belong to the right registration?** Each example needs the key for a worker registered for its own type.
4. **Does it have access?** For Private jobs, register the worker and submit the job under the same account.
5. **Is it already busy?** Each supplied worker processes one job at a time.

If retries were enabled by an administrator, a Pending job can also be waiting for its scheduled retry time.

## The worker exits or cannot connect

Read its terminal message, then check its `.env`:

| Symptom | First checks |
| --- | --- |
| Invalid worker configuration | Save the correct `.env` beside that worker's `worker.py`; fill in `API_KEY` and `API_URL`. |
| API connection failed | Check the readiness address from step 1, keep Docker running, and use port **8000** as the local worker API address. |
| HTTP 401 or 403 | Check that you pasted the worker API key, rather than an account password or sign-in token. |
| An outcome is rejected after a long task | The execution window may have expired. Use a worker that sends heartbeats for long tasks. |

The examples stop after HTTP or connection errors. Correct the problem and run `uv run --locked python worker.py` again. Check the job in the interface first: a result may have been accepted even if the worker did not receive the response. Restarting the process does not let it reclaim a still-Running attempt or revive a finished job.

If you set `API_KEY` or `API_URL` as terminal environment variables earlier, those values override the worker's `.env`. Use a fresh terminal without those overrides when testing your file settings.

## A job stays Running after the worker stops

Keep the **recovery** service running. With the tutorial defaults, the initial execution window is 120 seconds, and recovery checks for expired attempts about every five seconds. A previous heartbeat can change the expiry time. Recovery marks abandoned attempts Lost; with the default one-attempt limit, the job becomes Failed.

Check **View attempt history** and the stored error. Fix the cause before creating a new job. The interface currently has no cancel or manual retry button.

## A job seems to have disappeared

Select **Jobs → All statuses**, clear unwanted filters, and check the next page if needed. A finished job is no longer in Pending. Confirm you are signed in to the account that created it, or an account with access.

If a details page says **Job unavailable**, the ID may be incorrect or your account may lack permission. A saved bookmark uses the same permissions as the job list.

## Sharing work with another person

For your own local walkthrough, **Private** is sufficient. To collaborate, choose an appropriate **Access policy** when submitting a job:

| Policy in the form | Effect beyond your own access |
| --- | --- |
| **Permitted users** | Listed users can read the job, and their compatible workers can process it. |
| **Permitted workers** | Listed workers can process it; their owners do not automatically gain read access. |
| **Permitted workers and users** | Combines both kinds of grant. |
| **All users and workers** | Any signed-in user can read it, and any compatible authenticated worker can process it. |

Enter existing user or worker IDs in the fields that appear, separated by commas or whitespace. A collaborator can get their user ID from `GET /users/me/` in the [interactive API documentation](http://127.0.0.1:8000/docs), after using **Authorize** to sign in; a worker ID appears on its Worker details page.

Only grant access to people or workers you intend to share the parameters and results with. Worker registration visibility is a separate setting: making a worker visible to someone does not grant it access to that person's Private jobs.

## Orqbit does not start

First check that Docker Desktop is running in Linux-container mode and `.env.compose` has been saved. Inspect the services and their recent messages from the repository root:

```powershell
docker compose --env-file .env.compose ps --all
docker compose --env-file .env.compose logs --tail 80 db migrate api frontend recovery
```

Common causes:

- **Signing-key validation:** `SECRET_KEY` must contain exactly 64 lowercase hexadecimal characters. Generate it using step 1.
- **Database login failure:** for a new installation, the password must match in `POSTGRES_PASSWORD` and `DATABASE_URL`. For an existing database, restore its original settings rather than deleting the volume.
- **Port already in use:** another program may be using `8000` or `8080`. Stop that program if appropriate. If you change `API_PORT` in `.env.compose`, use the new port in the worker's `API_URL` and readiness address too.
- **Initial startup timeout:** image downloads or a slow first build may take longer. Read the logs, then rerun the startup command; you can increase `--wait-timeout 120` to `--wait-timeout 300`.

If you need help, share the error message after removing any passwords, tokens, keys, or private job data. Keep your configuration files private.

For installation without Docker, use the [backend local setup](../docs/development.md#running-the-api-locally) and [frontend local setup](../frontend/docs/development.md#without-docker-powershell). For application integrations, continue with the [API reference](../docs/api.md).

[Back to the tutorial index](README.md)
