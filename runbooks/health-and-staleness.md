# Health probes and stale telemetry

Liveness without a database query can stay healthy while requests fail. Check database readiness, latency, error count and when metrics were sampled. Report stale or absent data rather than inventing a cause. Transport status zero is a connection error and not an HTTP 5xx response.
