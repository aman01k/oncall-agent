"""Bounded concurrent traffic with a fixed seed; no model/API usage."""
from __future__ import annotations

import argparse
import asyncio
import random
import signal
import time

import httpx

from lab import metrics, now


async def run(url, rps, concurrency, seed, duration):
    rng = random.Random(seed)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    semaphore = asyncio.Semaphore(concurrency)
    pending = set()
    results = []

    async with httpx.AsyncClient(base_url=url, timeout=8, trust_env=False) as client:
        async def send(checkout, customer):
            async with semaphore:
                start = time.perf_counter()
                route = "/checkout" if checkout else "/orders/history"
                try:
                    if checkout:
                        response = await client.post(route, json={"customer_id": customer, "items": [{"sku": "SKU-1001", "qty": 1}]})
                    else:
                        response = await client.get(route, params={"customer_id": customer})
                    status = response.status_code
                except httpx.RequestError:
                    status = 0  # Transport failures are distinct from HTTP 5xx.
                results.append((now(), route, status, round((time.perf_counter() - start) * 1000, 2)))

        def flush():
            if results:
                with metrics() as conn:
                    conn.executemany("INSERT INTO requests VALUES (?, ?, ?, ?)", results)
                results.clear()

        start = time.monotonic()
        last_flush = start
        while not stopped.is_set() and (not duration or time.monotonic() - start < duration):
            if len(pending) < concurrency:
                task = asyncio.create_task(send(rng.random() < 0.55, f"customer-{rng.randrange(100)}"))
                pending.add(task)
                task.add_done_callback(pending.discard)
            if time.monotonic() - last_flush >= 1:
                flush()
                last_flush = time.monotonic()
            try:
                await asyncio.wait_for(stopped.wait(), timeout=1 / rps)
            except TimeoutError:
                pass
        await asyncio.gather(*pending)
        flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--rps", type=float, default=15)
    parser.add_argument("--concurrency", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--duration", type=float, default=0)
    args = parser.parse_args()
    if args.rps <= 0 or args.concurrency < 1 or args.duration < 0:
        parser.error("rps and concurrency must be positive; duration must be nonnegative")
    asyncio.run(run(args.url, args.rps, args.concurrency, args.seed, args.duration))
