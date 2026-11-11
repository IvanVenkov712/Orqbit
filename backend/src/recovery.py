"""Retry transient scan failures, bounding consecutive errors without SQLSTATE."""

import logging
from time import sleep

from sqlalchemy.exc import OperationalError

from config import settings
from database import SessionLocal
from services.job_execution import recover_expired_attempts

logger = logging.getLogger(__name__)


def main() -> None:
    unknown_failures = 0
    while True:
        try:
            with SessionLocal() as session:
                recover_expired_attempts(session)
        except OperationalError as error:
            # Startup/authentication failures can also lack SQLSTATE.
            sqlstate = getattr(error.orig, "sqlstate", None)
            if sqlstate is None:
                unknown_failures += 1
                if unknown_failures >= settings.max_unknown_database_errors:
                    logger.exception(
                        "Recovery stopped after %s consecutive errors without SQLSTATE",
                        unknown_failures,
                    )
                    raise
            else:
                unknown_failures = 0
                if not (
                    sqlstate.startswith(("08", "40", "53"))
                    or sqlstate in {"57P01", "57P02", "57P03"}
                ):
                    raise
            logger.exception("Recovery scan failed; retrying after the interval")
        else:
            unknown_failures = 0

        sleep(settings.recovery_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig()
    main()
