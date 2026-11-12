# 1. Install and open Orqbit

[Tutorial home](README.md) · [Next: Create your account →](02-create-your-account.md)

**Goal:** open Orqbit's sign-in page in your browser.

## Install the prerequisites

1. Install [Git](https://git-scm.com/downloads/) to download Orqbit.
2. Install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/). Follow its setup prompts, including WSL 2 if requested on Windows, and restart your computer if the installer asks. For another operating system, choose its guide from the [Docker Desktop installation pages](https://docs.docker.com/desktop/).
3. Open Docker Desktop and wait until its engine is running. On Windows, use **Linux containers**.
4. Open a new PowerShell window. On macOS or Linux, use your terminal.

Check that the tools are available:

```powershell
git --version
docker version
docker compose version
```

`docker version` should show both **Client** and **Server** information. If it reports that it cannot connect, start Docker Desktop before continuing. Use a current Docker Compose version that supports `up --wait`.

## Download Orqbit

Choose a folder where you keep projects, open a terminal there, and run:

```powershell
git clone https://github.com/IvanVenkov712/Orqbit.git
cd Orqbit
```

This `Orqbit` folder is the **repository root**. Whenever this tutorial says “from the repository root,” it means this folder, containing `docker-compose.yml`.

If you already have a checkout, open its root instead. Keep existing configuration files; the following copy step is for a new installation.

## Set up your local configuration

In PowerShell:

```powershell
Copy-Item .env.compose.example .env.compose
```

On macOS or Linux:

```sh
cp .env.compose.example .env.compose
```

Open `.env.compose` in a text editor. On Windows, you can run `notepad .env.compose`.

Choose a local database password using letters and digits for this walkthrough. Replace `change_this_local_password` **in both places**: `POSTGRES_PASSWORD` and `DATABASE_URL`. Keep the other parts of the URL unchanged, including `db`.

Generate a separate signing key in PowerShell:

```powershell
$keyBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($keyBytes)
$rng.Dispose()
-join ($keyBytes | ForEach-Object { $_.ToString("x2") })
```

On macOS or Linux, use:

```sh
openssl rand -hex 32
```

Copy the resulting 64-character string into `.env.compose`, replacing `replace_with_secret_key` on the `SECRET_KEY=` line. This lets Orqbit create sign-in sessions. Keep this file private and save it before continuing.

Leave the other settings at their example values, including `API_PORT=8000` and `MAX_ATTEMPTS=1`. These settings are enough for the tutorial. Your database password and signing key are installation settings; you will choose a separate account password in the next step.

## Start the system

From the repository root:

```powershell
docker compose --env-file .env.compose config --quiet
docker compose --env-file .env.compose up --build --wait --wait-timeout 120 frontend recovery
```

The first command finishes quietly when the configuration is valid. The second downloads and builds the application, prepares its database, and starts the web interface, API, and background recovery process. The initial download can take a few minutes.

Check the services:

```powershell
docker compose --env-file .env.compose ps --all
```

The database, API, frontend, and recovery services should be running; the API should be healthy. The `migrate` service finishing with **Exited (0)** is expected: its setup work is complete.

Open these addresses:

| Address | What you should see |
| --- | --- |
| [http://localhost:8080](http://localhost:8080) | Orqbit's sign-in page. This is the interface you will use. |
| [http://127.0.0.1:8000/health/ready](http://127.0.0.1:8000/health/ready) | `{"status":"ready"}`. This confirms that the API and database are ready. |

The containers keep running after the command finishes. Keep Docker Desktop open. You can close this terminal and use another one later.

If startup fails, see [startup troubleshooting](08-everyday-use-and-troubleshooting.md#orqbit-does-not-start). This walkthrough is for local use; making the installation available on the internet requires separate deployment setup.

**Ready:** you can open the sign-in page and the readiness check succeeds.

[Continue to 2. Create your account →](02-create-your-account.md)
