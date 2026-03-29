from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


LOGGER = logging.getLogger("upload_api")


def configure_logging() -> None:
    if LOGGER.handlers:
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(level: int, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        **fields,
    }
    LOGGER.log(level, json.dumps(payload, default=str, sort_keys=True))
