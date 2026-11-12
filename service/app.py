"""checkout-api: the small service that OnCall Agent investigates.

Run (no --reload, no --workers, so the PID stays stable for the supervisor):
    .venv/bin/python -m uvicorn service.app:app --port 8001 --no-access-log

Endpoints that touch the database are plain `def` on purpose. FastAPI runs
them in a thread pool (40 threads by default), so many requests can wait on
the database connection pool at the same time. With `async def` and a
blocking driver, requests would run one at a time and the pool would never
run out.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from . import config, db, logs
from .logs import log, utc_now
from .pricing import price_total
from .cache import record_checkout

settings = config.load()
logger = logs.setup(settings.log_file, settings.service_name, settings.version)
engine = db.make_engine(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_schema(engine)
    log(logger, logging.INFO, "service started", event="startup", version=settings.version)
    yield
    log(logger, logging.INFO, "service stopping", event="shutdown")
    engine.dispose()


app = FastAPI(title="checkout-api", lifespan=lifespan)


# --- Request logging -------------------------------------------------------

@app.middleware("http")
async def request_log(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001 - every unhandled error becomes a logged 500
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        log(logger, logging.ERROR, "unhandled error", exc_info=(type(exc), exc, exc.__traceback__),
            event="request", request_id=request_id, method=request.method,
            route=request.url.path, status=500, latency_ms=latency_ms)
        response = JSONResponse({"error": "internal_error", "request_id": request_id}, status_code=500)
        response.headers["x-request-id"] = request_id
        return response
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    level = logging.ERROR if response.status_code >= 500 else logging.INFO
    log(logger, level, "request", event="request", request_id=request_id, method=request.method,
        route=request.url.path, status=response.status_code, latency_ms=latency_ms)
    response.headers["x-request-id"] = request_id
    return response


# --- Health ----------------------------------------------------------------

@app.get("/health")
async def health():
    """Liveness only: answers even when the database is stuck."""
    return {"status": "ok", "service": settings.service_name, "time": utc_now()}


@app.get("/health/db")
def health_db():
    """Readiness: needs a database connection within the pool timeout."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "pool_checked_out": engine.pool.checkedout()}


# --- Business endpoints ----------------------------------------------------

class Item(BaseModel):
    sku: str
    qty: int = Field(gt=0, le=100)


class CheckoutRequest(BaseModel):
    customer_id: str
    currency: str = "USD"
    items: list[Item] = Field(min_length=1)


@app.post("/checkout")
def checkout(req: CheckoutRequest):
    record_checkout(req.customer_id)
    with engine.begin() as conn:
        skus = [i.sku for i in req.items]
        rows = conn.execute(
            text("SELECT sku, price FROM products WHERE sku IN :skus").bindparams(
                bindparam("skus", expanding=True)),
            {"skus": skus},
        ).all()
        prices = {r.sku: r.price for r in rows}
        missing = [s for s in skus if s not in prices]
        if missing:
            raise HTTPException(status_code=400, detail=f"unknown sku: {missing}")
        total = price_total(prices, req.items, req.customer_id)
        result = conn.execute(
            text("INSERT INTO orders (customer_id, total, currency, created_at)"
                 " VALUES (:c, :t, :cur, :ts)"),
            {"c": req.customer_id, "t": total, "cur": req.currency, "ts": utc_now()},
        )
        order_id = result.lastrowid
    return {"order_id": order_id, "total": total, "currency": req.currency}


@app.get("/orders/history")
def orders_history(customer_id: str, limit: int = 20):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, total, currency, created_at FROM orders"
                 " WHERE customer_id = :c ORDER BY id DESC LIMIT :n"),
            {"c": customer_id, "n": limit},
        ).all()
        if settings.history_query_delay_s > 0:
            # Holds the connection while "the query runs".
            time.sleep(settings.history_query_delay_s)
    return {"customer_id": customer_id, "orders": [dict(r._mapping) for r in rows]}
