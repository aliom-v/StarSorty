import logging
import os
import sys

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logging.getLogger("scheduler").warning(
            "Invalid %s=%r, fallback to %.2f",
            name,
            raw,
            default,
        )
        return default
    if minimum is not None and value < minimum:
        logging.getLogger("scheduler").warning(
            "Out-of-range %s=%r, fallback to %.2f",
            name,
            raw,
            default,
        )
        return default
    return value


API_BASE_URL = os.getenv("API_BASE_URL", "http://api:4321")
SYNC_CRON = os.getenv("SYNC_CRON", "0 */6 * * *")
SYNC_TIMEOUT = _env_float("SYNC_TIMEOUT", 30.0, minimum=0.1)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")


def trigger_sync() -> None:
    url = f"{API_BASE_URL.rstrip('/')}/sync"
    try:
        logger.info("Triggering sync: %s", url)
        headers = {"X-Admin-Token": ADMIN_TOKEN} if ADMIN_TOKEN else None
        response = requests.post(url, timeout=SYNC_TIMEOUT, headers=headers)
        logger.info("Sync response %s: %s", response.status_code, response.text[:500])
    except Exception as exc:
        logger.error("Sync failed: %s", exc)


def main() -> None:
    try:
        trigger = CronTrigger.from_crontab(SYNC_CRON)
    except Exception as exc:
        logger.error("Invalid SYNC_CRON '%s': %s", SYNC_CRON, exc)
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(trigger_sync, trigger)
    logger.info("Scheduler started with cron: %s", SYNC_CRON)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
