# 9. Register a producer (optional)

[← Everyday use and troubleshooting](08-everyday-use-and-troubleshooting.md) · [Tutorial home](README.md) · [Next: Start your producer →](10-start-your-producer.md)

**Goal:** give a separate submission program its own identity and save its API key.

A **producer** sends jobs to Orqbit and can read their status and result. A **worker** executes them. In the main walkthrough, you submitted through the browser; now you will let a Python program submit the same kind of job.

You need a running Orqbit installation and a signed-in account from [steps 1–2](README.md#follow-these-steps). Use the **same account that owns your addition worker**: the supplied producer submits Private jobs.

## Create the registration

1. Select **Producers** in the sidebar.
2. Select **Create a producer**.
3. In **Producer name**, enter `my-producer`, or another unused name.
4. Select **Create producer**.

Names must be globally unique and contain 3–16 Latin letters, digits, underscores, or hyphens. If the name is taken, choose another. This name labels your application; you do not need to declare supported job types for a producer.

## Save the key

The confirmation displays a **Producer API key**. Select **Copy API key** and save it securely before leaving or reloading. Then choose **I've saved the key — view producer**.

The original key cannot be retrieved later. Keep it private; you will paste it into the producer's own `.env` in the next step. A producer key, a worker key, and a user sign-in token serve different purposes. Use the producer key for this program.

**Active** means the registration's credentials are enabled. Registration does not start a program or submit a job.

## If you lose the key

Open **Producers**, select your producer, choose **Reissue API key**, and confirm with **Confirm reissue**. Save the replacement key, update the producer's `.env`, and restart the program. The previous key stops working immediately. Reissuing preserves the producer's identity and existing jobs; it does not reactivate an inactive registration.

For an API-based alternative, use your **user bearer token** with `POST /producers` and body `{"name":"my-producer"}`, then save the returned `secret_api_key`. See [producer management](../../docs/api.md#producer-management). The producer key itself cannot register or manage producers.

**Ready:** you have a producer registration and its saved API key. No producer process is running yet.

[Continue to 10. Start your producer →](10-start-your-producer.md)
