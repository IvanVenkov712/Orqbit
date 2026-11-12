# Build a worker with leases and heartbeats

[All tutorials](../README.md) · [Getting started with Orqbit](../getting-started/README.md)

Build your own **delayed greeting** worker, using the same small, independent Python application structure as the supplied examples. It will accept a name, wait while sending heartbeats, then return `{"greeting":"Hello, Taylor!","waited_seconds":150}`.

The delay makes lease renewal easy to observe. Later, replace the waiting task with your own work, using the guidance in the final step.

## Before you start

You need Orqbit running, an account, Python 3.13, and uv. Complete [installation](../getting-started/01-install-and-open.md), [account setup](../getting-started/02-create-your-account.md), and [worker prerequisites](../getting-started/04-start-your-worker.md#install-uv-and-python) first if necessary. This tutorial assumes the local API is at `http://127.0.0.1:8000` and the interface is at `http://localhost:8080`.

Commands use PowerShell, with macOS/Linux alternatives where needed. Run them from the directory specified in each step. Put Python listings in the named files using your editor.

## Follow these steps

| Step | Guide | Outcome |
| --- | --- | --- |
| 1 | [Create an independent worker](01-create-the-worker.md) | Your own directory, dependencies, configuration, and polling loop. |
| 2 | [Implement lease renewal](02-implement-heartbeats.md) | Deadline checks and cooperative heartbeats. |
| 3 | [Execute work and report outcomes](03-execute-and-report.md) | A greeting task that stops when its lease is lost. |
| 4 | [Test without real delays](04-test-the-worker.md) | Tests for renewal, expiry, lost ownership, and invalid input. |
| 5 | [Register, run, and observe](05-run-and-observe.md) | A real job that outlasts its initial lease and saves its result. |

## The protocol in one minute

A **lease** is a deadline for a particular execution attempt. A **heartbeat** asks the server to renew that deadline while you are still working.

```text
Claim an attempt -> Read its lease_expires_at
                         |
                  Check deadline
                         |
                  Do a short work step
                         |
                  Check deadline again
                         |
          More work? ---- yes -> Heartbeat -> Use returned deadline -> Repeat
              |
              no -> Report outcome before expiry

At any step: expired deadline or uncertain ownership -> Stop without an outcome
```

The default initial lease is **120 seconds**. Heartbeat renewal uses a **60-second window from the server's current time**, without shortening an existing deadline. It does not add 60 seconds to the old deadline. Always use the returned deadline; your worker does not choose it.

This is an attempt heartbeat, not an online-status indicator for a worker process. The API remains authoritative: a local check can pass and the request can still arrive too late. An expired attempt cannot be revived by sending another heartbeat.

[Start with step 1 →](01-create-the-worker.md)
