"""Build a private Compose stack and verify persistence across recreation.

Run explicitly with `python tests/compose_smoke.py`; this is not a pytest test.
Only this run's randomly named Compose project and volume are removed.
"""

import argparse
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18000)
    args = parser.parse_args()

    project = f"orqbit-smoke-{uuid4().hex[:12]}"
    password = secrets.token_hex(16)
    environment = os.environ | {
        "POSTGRES_DB": "orqbit_smoke",
        "POSTGRES_USER": "orqbit_smoke",
        "POSTGRES_PASSWORD": password,
        "DATABASE_URL": (
            f"postgresql+psycopg://orqbit_smoke:{password}@db:5432/orqbit_smoke"
        ),
        "LEASE_SECONDS": "120",
        "PROTRACTION_SECONDS": "60",
        "SECRET_KEY": secrets.token_hex(32),
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "API_PORT": str(args.port),
    }

    def compose(*arguments: str) -> None:
        subprocess.run(
            ["docker", "compose", "--project-name", project, *arguments],
            cwd=ROOT,
            env=environment,
            check=True,
        )

    def request(
        path: str,
        payload: dict | None = None,
        expected_status: int = 200,
        headers: dict | None = None,
    ) -> dict | list:
        data = json.dumps(payload).encode() if payload is not None else None
        message = Request(
            f"http://127.0.0.1:{args.port}{path}",
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            response = urlopen(message, timeout=8)
        except HTTPError as error:
            if error.code != expected_status:
                raise
            response = error
        with response:
            assert response.status == expected_status
            return json.load(response)

    def wait_for_api() -> None:
        deadline = time.monotonic() + 30
        while True:
            try:
                assert request("/health/ready") == {"status": "ready"}
                return
            except (URLError, TimeoutError, ConnectionError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("API did not become available within 30 seconds")
                time.sleep(0.25)

    try:
        compose("config", "--quiet")
        compose("up", "--build", "--wait", "--wait-timeout", "120", "api")
        wait_for_api()
        assert request("/health/live") == {"status": "ok"}

        # Confirm the final image excludes development tools and environment files.
        compose(
            "run",
            "--rm",
            "--no-deps",
            "api",
            "python",
            "-c",
            "import importlib.util, os; from pathlib import Path; "
            "assert os.getuid() != 0; "
            "assert not list(Path('/app').glob('.env*')); "
            "assert all(importlib.util.find_spec(name) is None "
            "for name in ('pytest', 'ruff', 'httpx'))",
        )

        user_password = f"Aa1${secrets.token_hex(6)}"
        owner = request(
            "/auth/register",
            {
                "username": "smoke-user",
                "email": "smoke@example.com",
                "full_name": "Smoke test",
                "password": user_password,
            },
        )
        login = Request(
            f"http://127.0.0.1:{args.port}/auth/login",
            data=urlencode(
                {"username": "smoke-user", "password": user_password}
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(login, timeout=8) as response:
            token = json.load(response)["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        created = request(
            "/jobs/",
            {
                "job_type": "container-smoke",
                "params": {"nested": [True, None, "UTC"]},
                "permission_policy": "PRIVATE",
            },
            headers=auth_headers,
        )
        assert created["status"] == "PENDING"
        assert created["user_id"] == owner["id"]
        path = f"/jobs/{created['id']}"
        assert request(path, headers=auth_headers) == created

        # An explicit migration rerun must preserve the already committed job.
        compose("run", "--rm", "migrate")
        assert request(path, headers=auth_headers) == created

        # The API stays live during an actual database outage and recovers
        # without restarting its process or reusing broken pooled connections.
        compose("stop", "db")
        assert request("/health/live") == {"status": "ok"}
        assert request("/health/ready", expected_status=503) == {"status": "not_ready"}
        compose("up", "--wait", "--wait-timeout", "120", "db")
        wait_for_api()
        assert request(path, headers=auth_headers) == created

        compose("down")  # Retain the named PostgreSQL volume.
        compose("up", "--wait", "--wait-timeout", "120", "api")
        wait_for_api()
        assert request(path, headers=auth_headers) == created
        print(
            "Compose smoke check passed: migrated, ready, survived database outage, "
            "created/read, recreated, preserved."
        )
    except Exception:
        compose("logs", "--no-color")
        raise
    finally:
        compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
