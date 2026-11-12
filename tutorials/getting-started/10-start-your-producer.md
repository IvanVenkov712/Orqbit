# 10. Start your producer (optional)

[← Register a producer](09-register-a-producer.md) · [Tutorial home](README.md) · [Build your own producer →](../build-a-producer/README.md)

**Goal:** submit an addition job from a standalone program and read its result.

Keep Orqbit running. Start the [addition worker](04-start-your-worker.md) in its own terminal under the same account as your producer. If you stopped Orqbit after the main walkthrough, follow [the restart instructions](08-everyday-use-and-troubleshooting.md#stop-and-come-back-later) first. You also need Python 3.13 and uv from [step 4](04-start-your-worker.md#install-uv-and-python).

## Prepare the producer

Open a **new terminal at the repository root**:

```powershell
cd examples/producers/add_numbers_cli
uv sync --locked
```

Create the producer's configuration once:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux, use `cp .env.example .env`. If `.env` already exists, edit it instead of copying over it.

Open **`examples/producers/add_numbers_cli/.env`** and save:

```dotenv
API_KEY=PASTE_YOUR_PRODUCER_KEY_HERE
API_URL=http://127.0.0.1:8000
POLL_INTERVAL=2
REQUEST_TIMEOUT=10
```

Replace the placeholder with the key from [step 9](09-register-a-producer.md). This is a separate file from the worker's `.env` and the server's `.env.compose`. Use port **8000** for the local API; port 8080 serves the browser interface. Use the installation's API address if running elsewhere.

Keep the real `.env` private. Terminal environment variables override file values; remove old `API_KEY` or `API_URL` overrides, or use a fresh terminal without them.

## Submit and wait for the answer

Still inside `examples/producers/add_numbers_cli/`:

```powershell
uv run --locked python producer.py --wait --wait-timeout 30 2 3 5
```

With a compatible worker running, expect output like:

```text
Idempotency-Key: <generated UUID>
job_id: 42
status: SUCCEEDED
result: {"sum": 10}
```

Your UUID and job ID will differ. The producer sends numbers to Orqbit; the worker calculates their sum. The key is printed before submission so you can retain it if the response is lost. It is a submission identifier, separate from the secret API key.

In the browser, select **Jobs** and open the printed job ID to inspect the saved result and attempt history. Sign in as the account that owns the producer.

## Submit without waiting

```powershell
uv run --locked python producer.py 8 12
```

The command prints a submission key and job ID, then exits. This means submission was accepted, not that execution finished. Check the job in the browser later.

This CLI runs once per command. You do not need to register again for each run. Closing it, pressing Ctrl+C, or reaching the local waiting limit does **not** cancel accepted jobs.

## Repeat an uncertain submission safely

A connection failure can happen after Orqbit has saved the job. Reuse the **original printed key**, exact numbers in the same order, and same producer registration when repeating. For example, choose an unused key for a first submission, then repeat it:

```powershell
uv run --locked python producer.py --idempotency-key my-addition-001 2 3 5
uv run --locked python producer.py --idempotency-key my-addition-001 --wait 2 3 5
```

Both commands refer to the same job. Changing the numbers while reusing that key returns HTTP 409. Running without an explicit key generates a new one and submits a separate job. Keys share a namespace across the owning account's producers and browser submissions; use a fresh key for each new operation.

The CLI does not automatically retry or save keys locally. Keep the original key if you need to repeat after restarting.

## Common problems

| Symptom | What to check |
| --- | --- |
| Invalid producer configuration | Save `API_KEY` and `API_URL` in this producer's `.env`; timing values must be positive and finite. |
| HTTP 401 | Use an active producer's key, rather than a worker key or sign-in token. After key reissue, update `.env` and rerun. |
| API connection failed | Check that Orqbit is running and the API address is correct. If submission was attempted, repeat with its original key. |
| HTTP 409 | Check whether the key was reused with different numbers or by another producer/direct submission under your account. |
| HTTP 422 | Check the input and submission key; see the [CLI reference](../../examples/producers/add_numbers_cli/README.md). |
| HTTP 503 | The submission outcome may be uncertain. Repeat later using the original key and payload. |
| Waiting period expired | The job continues on the server. Inspect its ID in the browser; check the addition worker's terminal, `add_numbers` type, and ownership for Private jobs. |
| Status `FAILED` | Read the stored `error` and attempt history; a new submission key creates a new job rather than resuming the old one. |

To use the supplied continuously running producer instead, follow the [console producer guide](../../examples/producers/add_numbers_console/README.md). It accepts several lines while earlier jobs execute and has its own setup and retry behavior.

**Ready:** you can submit work through a producer program and inspect the outcome independently.

[Build an independent producer →](../build-a-producer/README.md) · [Back to the tutorial home](README.md)
