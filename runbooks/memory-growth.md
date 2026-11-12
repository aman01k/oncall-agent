# Growing memory and repeated worker restarts

Symptoms: RSS growth, HTTP 503, memory_limit_exceeded supervisor events and repeated worker_start. Inspect cache or request retention code. A restart only delays an unbounded allocation. A metadata-only deploy cannot fix a leak. Roll back the causal cache change and verify sustained memory stability.
