# 4. Start your worker

[← Register a worker](03-register-a-worker.md) · [Tutorial home](README.md) · [Next: Submit a job →](05-submit-your-first-job.md)

**Goal:** run the addition worker so it can process your jobs.

The worker runs in its own terminal. Docker continues running Orqbit separately.

## Install uv and Python

Install **uv** using its [official installation guide](https://docs.astral.sh/uv/getting-started/installation/). On Windows with WinGet available, you can use:

```powershell
winget install --id astral-sh.uv -e
```

Open a new terminal after installation, then run:

```powershell
uv --version
uv python install 3.13
```

uv can [install Python for you](https://docs.astral.sh/uv/guides/install-python/), so a separate Python installer is unnecessary for this walkthrough.

## Prepare the example

Open a terminal **at the repository root**, then enter the worker's folder:

```powershell
cd examples/workers/add_numbers
uv sync --locked
```

uv creates this worker's own environment and installs its dependencies. You do not need to activate that environment manually.

Create its configuration file once. In PowerShell:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```sh
cp .env.example .env
```

Open this new `.env` in a text editor. It is inside **`examples/workers/add_numbers/`**, separate from the server's `.env.compose` file.

```dotenv
API_KEY=PASTE_YOUR_WORKER_KEY_HERE
API_URL=http://127.0.0.1:8000
POLL_INTERVAL=2
REQUEST_TIMEOUT=10
```

Replace `PASTE_YOUR_WORKER_KEY_HERE` with the key saved in step 3, then save the file. Use the **API address on port 8000** for this local setup; port 8080 is the web interface. If using someone else's installation, ask for its API base address.

Keep `.env` private. Avoid overwriting it with the example file on later runs.

## Run the worker

Still inside `examples/workers/add_numbers/`:

```powershell
uv run --locked python worker.py
```

You should see:

```text
INFO: add_numbers worker started; press Ctrl+C to stop
```

**Leave this terminal running.** While the queue is empty, the worker quietly checks for a suitable job every two seconds. Silence after the startup message is normal. Once it processes a job, it logs a reported outcome.

Return to your browser to submit a job. Closing the browser does not stop the worker; closing its terminal does.

## Try a different supplied worker later

Finish the addition walkthrough first. When you want another example, register a **separate worker** in the interface with the matching supported type, save its new key, and repeat the setup commands inside its own folder.

| Folder under `examples/workers/` | Supported type | What to submit |
| --- | --- | --- |
| [`add_numbers`](../examples/workers/add_numbers/README.md) | `add_numbers` | A `numbers` list containing Number items. `[2, 3, 5]` returns `{"sum":10}`. |
| [`count_primes`](../examples/workers/count_primes/README.md) | `count_primes` | A Number parameter named `limit`, with value `100`. Returns `{"limit":100,"count":25}`. Use a whole number. |
| [`csv_summary`](../examples/workers/csv_summary/README.md) | `csv_summary` | CSV text and a list of column names; see the short recipe below. |
| [`delay_with_heartbeat`](../examples/workers/delay_with_heartbeat/README.md) | `delay_with_heartbeat` | No parameters. Waits 150 seconds by default and returns `{"waited_seconds":150}`. Useful for watching Running status. |
| [`delay`](../examples/workers/delay/README.md) | `delay` | No parameters. Set `EXECUTION_DELAY=5` in its `.env` for a short successful job. Its default 150-second delay deliberately exceeds the default execution window. |

For each example, copy **its own** `.env.example` so any extra settings are included. Do not register an example for types its program does not implement. If you want several examples running at once, give each a separate terminal and key.

For a small CSV example, create a `csv_summary` job in the parameter editor:

- Add `csv` with type **Text**, and paste these three lines as its value:

  ```csv
  name,amount
  A,10
  B,20
  ```

- Add `columns` with type **List**, then add one **Text** item with value `amount`.

The result should have `row_count: 2` and, under `columns.amount`, a sum of `30` and mean of `15`. The CSV is pasted text; this example does not upload a file.

**Ready:** your addition worker is running and waiting for jobs.

[Continue to 5. Submit your first job →](05-submit-your-first-job.md)
