# 5. Register, run, and observe

[← Test the worker](04-test-the-worker.md) · [Tutorial home](README.md)

## Register your worker

Sign in to the web interface and open **Workers → Register a worker**. Use:

| Field | Value |
| --- | --- |
| Worker name | `my-greeter-hb`, or another unused name of 3–16 letters, digits, underscores, or hyphens. |
| Supported types | `delayed_greeting` |
| Visibility policy | **Private** |

Save the one-time API key before leaving. See the [registration walkthrough and screenshot](../getting-started/03-register-a-worker.md) if needed. Registering does not start the program.

## Configure and start it

From **`examples/workers/delayed_greeting/`**, create the private configuration once:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux, use `cp .env.example .env`.

Edit `.env`: paste the new worker's key into `API_KEY` and keep `API_URL=http://127.0.0.1:8000` for the local setup. Keep `EXECUTION_DELAY=150`, `HEARTBEAT_INTERVAL=10`, and `REQUEST_TIMEOUT=10`.

On the server, keep the standard `LEASE_SECONDS=120`, `LEASE_EXTENSION_SECONDS=60`, and `MAX_ATTEMPTS=1` for this demonstration. If you changed `.env.compose`, recreate the services from the repository root:

```powershell
docker compose --env-file .env.compose up --build --wait --wait-timeout 120 frontend recovery
```

Back in the worker directory, run:

```powershell
uv run --locked python worker.py
```

Leave its terminal open. An empty queue produces no heartbeat messages: heartbeats begin only after a claim.

## Submit a greeting job

Using the same account, open **Jobs → Submit a job**:

1. Set **Job type** to `delayed_greeting`.
2. Add a parameter named `name`, choose **Text**, and enter `Taylor`.
3. Keep **Private** access and select **Submit job**.

This builds the parameters `{"name":"Taylor"}`. Do not add a duration parameter; the worker's `EXECUTION_DELAY` controls the wait.

Watch the Job details page and worker terminal. You should see renewal messages like:

```text
INFO: Renewed lease for attempt ... until ...
```

The job stays Running past the initial 120-second lease and normally succeeds after about 150 seconds. Under **Outcome → Result**, expect:

```json
{
  "greeting": "Hello, Taylor!",
  "waited_seconds": 150
}
```

`waited_seconds` records the configured delay, not a measured completion time. HTTP and scheduling overhead can make the total time longer.

Use **View attempt history** to confirm the successful attempt. Finished jobs appear under **All statuses** or **Succeeded**, rather than the default Pending view. Screenshots of these controls are in [Progress and results](../getting-started/06-progress-and-results.md).

## Observe an abandoned attempt

For an optional failure exercise, submit another greeting, wait until it is Running, then press **Ctrl+C** in the worker terminal. This interrupts work without reporting an outcome.

Keep the server and recovery process running. After the last accepted lease deadline and a recovery scan, the attempt becomes **Lost**. With `MAX_ATTEMPTS=1` saved on that job, the job becomes **Failed**. A heartbeat may have extended the deadline, so stopping the process does not immediately change its status.

If retries were enabled when the job was created, recovery may instead schedule another attempt after a delay. Restarting this program lets it claim eligible pending work; it does not resume its abandoned attempt. Tests in step 4 exercise actual heartbeat rejection without unreliable manual timing or waiting for minutes.

## Adapt this to real work

The example's short sleeps are cooperative work steps. For a CPU task, use bounded batches and check the deadline between batches, as in the [count_primes execution code](../../examples/workers/count_primes/execution.py). Renew when the scheduled heartbeat time arrives, and check again before reporting.

Choose steps short enough to leave room for an HTTP request before expiry. Merely surrounding a long blocking function with checks will not send heartbeats while that function runs. For HTTP-based work, bound individual request times too. The waiting helper here does not run concurrently with your task.

On lease loss, stop starting new work and let `LeaseLost` reach the main loop. A heartbeat cannot undo an email, payment, or file write already performed. If your task changes another system, design that operation to avoid duplicate effects using a stable job or business-operation identifier across attempts. Leases do not provide exactly-once execution.

Keep task parameters and results JSON-compatible, and keep dependencies, configuration, and tests in the worker's own directory. Never import backend code or connect directly to Orqbit's database. There is currently no hard execution deadline: successful renewals can keep an attempt leased indefinitely.

For exact request formats and error codes, consult the [attempt heartbeat and lease protocol](../../docs/api.md#attempt-heartbeats-and-leases). For ordinary stopping, restarting, and connection problems, see [everyday use and troubleshooting](../getting-started/08-everyday-use-and-troubleshooting.md).

[Back to all tutorials](../README.md)
