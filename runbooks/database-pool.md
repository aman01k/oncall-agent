# Database connection pool timeouts

Symptoms: QueuePool TimeoutError, long request latency, healthy liveness but unhealthy database readiness. Inspect pool_size, max_overflow and slow queries retaining connections. A restart does not fix a too-small pool. Check the config diff and propose rollback. Do not increase connections blindly.
