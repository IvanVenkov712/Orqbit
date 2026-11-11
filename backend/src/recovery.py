from time import sleep

from config import settings
from database import SessionLocal
from services.job_execution import recover_expired_attempts

if __name__ == "__main__":
    while True:
        with SessionLocal() as session:
            recover_expired_attempts(session)

        sleep(settings.recovery_interval_seconds)