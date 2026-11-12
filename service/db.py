"""Database setup: SQLite file through SQLAlchemy with an explicit QueuePool.

QueuePool (not SQLite's default pool) is what makes connection-pool
exhaustion possible: when every connection is checked out, a new request
waits up to pool_timeout and then raises sqlalchemy.exc.TimeoutError.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.pool import QueuePool

from .config import Settings

PRODUCTS = [
    ("SKU-1001", "Coffee beans 1kg", 18.50),
    ("SKU-1002", "Paper filters x100", 4.25),
    ("SKU-1003", "Ceramic mug", 9.00),
    ("SKU-1004", "Hand grinder", 39.90),
]


def make_engine(settings: Settings) -> Engine:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{settings.db_path}",
        poolclass=QueuePool,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_s,
        connect_args={"check_same_thread": False, "timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


def init_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS products ("
            " sku TEXT PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL)"
        ))
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS orders ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT NOT NULL,"
            " total REAL NOT NULL, currency TEXT NOT NULL, created_at TEXT NOT NULL)"
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)"))
        conn.execute(
            text("INSERT OR IGNORE INTO products (sku, name, price) VALUES (:sku, :name, :price)"),
            [{"sku": s, "name": n, "price": p} for s, n, p in PRODUCTS],
        )
