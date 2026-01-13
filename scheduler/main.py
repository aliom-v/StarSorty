import logging
import os
import sys

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
SYNC_CRON = os.getenv("SYNC_CRON", "0 */6 * * *")
SYNC_TIMEOUT = float(os.getenv("SYNC_TIMEOUT", "30"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")


def trigger_sync() -> None:
    url = f"{API_BASE_URL.rstrip('/')}/sync"
    try:
        logger.info("Triggering sync: %s", url)
        response = requests.post(url, timeout=SYNC_TIMEOUT)
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
