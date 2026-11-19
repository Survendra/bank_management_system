import logging
import os
import time

from app import process_due_scheduled_transfers


def main():
    interval = float(os.environ.get("SCHEDULED_TRANSFER_POLL_SECONDS", "15"))
    if not 1 <= interval <= 3600:
        raise ValueError(
            "SCHEDULED_TRANSFER_POLL_SECONDS must be between 1 and 3600."
        )

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("scheduled_transfer_worker")
    logger.info("Scheduled-transfer worker started.")

    while True:
        try:
            count = process_due_scheduled_transfers()
            if count:
                logger.info("Processed %s scheduled transfer(s).", count)
        except Exception:
            logger.exception("Scheduled-transfer polling cycle failed.")
        time.sleep(interval)


if __name__ == "__main__":
    main()
