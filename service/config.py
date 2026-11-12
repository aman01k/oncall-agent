"""Service settings, read from environment variables with safe defaults.

The fault versions of the service (built later into the sandbox repo) change
these defaults in code, so the agent cannot see a fault switch anywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    service_name: str
    version: str
    db_path: Path
    log_file: Path
    pool_size: int
    max_overflow: int
    pool_timeout_s: float
    # Time /orders/history holds its database connection (simulates a slow query).
    history_query_delay_s: float


def load() -> Settings:
    """Read settings from the environment at call time (not at import time)."""
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "checkout-api"),
        version=os.getenv("SERVICE_VERSION", "dev"),
        db_path=Path(os.getenv("APP_DB", ROOT / "data" / "app.db")),
        log_file=Path(os.getenv("LOG_FILE", ROOT / "data" / "logs" / "service.jsonl")),
        pool_size=_int("POOL_SIZE", 5),
        max_overflow=_int("MAX_OVERFLOW", 5),
        pool_timeout_s=_float("POOL_TIMEOUT", 2.0),
        history_query_delay_s=_float("HISTORY_QUERY_DELAY", 0.0),
    )
