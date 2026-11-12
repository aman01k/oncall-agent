"""Local webhook entry point with bounded background investigation jobs."""
from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent.runner import ROOT, investigate

app = FastAPI(title="OnCall Agent alert intake")
pool = ThreadPoolExecutor(max_workers=1)
slot = threading.BoundedSemaphore(2)


class AlertInput(BaseModel):
    snapshot: str


@app.post("/alerts", status_code=202)
def alert(payload: AlertInput):
    source = (ROOT / payload.snapshot).resolve()
    allowed = [ROOT / "eval/fixtures", ROOT / "data/snapshots"]
    if not any(source.is_relative_to(path) for path in allowed) or not (source / "alert.json").is_file():
        raise HTTPException(400, "Use a captured snapshot under eval/fixtures or data/snapshots")
    if not slot.acquire(blocking=False):
        raise HTTPException(429, "Investigation queue is full")
    run_id = uuid.uuid4().hex

    def work():
        try:
            investigate(source, output=ROOT / "runs" / run_id)
        finally:
            slot.release()

    pool.submit(work)
    return {"run_id": run_id, "status": "queued"}
