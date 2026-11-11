"""Scan expired leases, retrying transient database failures after the interval."""

import logging
from time import sleep

from sqlalchemy.exc import OperationalError

from config import settings
from database import SessionLocal
from services.job_execution import recover_expired_attempts

logger = logging.getLogger(__name__)


def main() -> None:
    while True:
        try:
            with SessionLocal() as session:
                recover_expired_attempts(session)
        except OperationalError as error:
            # Connection failures can have no SQLSTATE (e.g. connection refused).
            sqlstate = getattr(error.orig, "sqlstate", None)
            if sqlstate is not None and not (
                sqlstate.startswith(("08", "40", "53"))
                or sqlstate in {"57P01", "57P02", "57P03"}
            ):
                raise
            logger.exception("Recovery scan failed; retrying after the interval")

        sleep(settings.recovery_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig()
    main()
