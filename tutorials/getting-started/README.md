# Your first job with Orqbit

[All tutorials](../README.md) · [Build a worker with leases and heartbeats](../worker-leases-and-heartbeats/README.md)

Welcome! This tutorial takes you from a fresh installation to a finished job whose result you can read in your browser. You do not need to know FastAPI, databases, or Docker internals.

You will start with the included **add numbers** worker. Give it `2`, `3`, and `5`, and Orqbit will save the answer, `10`. After that, you can try other examples or build a worker of your own.

## How the workflow fits together

Three things work together:

| Part | What it does |
| --- | --- |
| The web interface | Lets you create an account, register workers, submit jobs, and read results. |
| The Orqbit server | Saves jobs, gives eligible jobs to workers, and records their outcomes. |
| A worker | A separate program you run that asks for work, does it, and sends the answer back. |

The everyday workflow is:

```text
Create an account -> Register a worker -> Run the worker
                                              |
Submit a job -> Pending -> Running -> Succeeded -> Read the result
                                 \-> Failed   -> Read the error
```

**Registering a worker and running it are two separate steps.** Registration gives the program its own API key, which acts like a password. Starting the program is what makes it available to process jobs. You can submit jobs before starting a worker; they wait in the queue.

## Follow these steps

| Step | Guide | You will finish with… |
| --- | --- | --- |
| 1 | [Install and open Orqbit](01-install-and-open.md) | The web interface running on your computer. |
| 2 | [Create your account](02-create-your-account.md) | A signed-in workspace. |
| 3 | [Register a worker](03-register-a-worker.md) | A worker registration and its saved API key. |
| 4 | [Start your worker](04-start-your-worker.md) | A program ready to process your jobs. |
| 5 | [Submit your first job](05-submit-your-first-job.md) | An addition job with your chosen numbers. |
| 6 | [Follow progress and read the result](06-progress-and-results.md) | A saved result, plus an understanding of errors and attempts. |
| 7, optional | [Create your own worker](07-create-your-own-worker.md) | A small Python worker that greets someone by name. |
| 8 | [Stop, restart, and solve common problems](08-everyday-use-and-troubleshooting.md) | The commands and checks you will use next time. |

Steps 1–6 are the main walkthrough. Step 7 is for readers who want to write a little Python; you can use the supplied workers without doing it.

## Before you begin

Use a computer where you can install software and an internet connection for the initial downloads. The main installation uses Docker Desktop; the example workers use Python and uv, a tool that prepares their dependencies. We will install those when needed. Node.js and a separate PostgreSQL installation are unnecessary for this route.

Commands use **Windows PowerShell**. Where a command differs on macOS or Linux, an alternative is included. Paste only the contents of command blocks into your terminal. Edit configuration and Python code blocks in a text editor.

The screenshots show the actual Orqbit interface with demonstration data. Your usernames, job IDs, dates, and worker names will differ. No worker API keys are included in the images.

If someone has already provided an Orqbit installation, use their web address and skip to [step 2](02-create-your-account.md). Ask them for the API address as well if you will run a worker.

**Start here: [1. Install and open Orqbit →](01-install-and-open.md)**
