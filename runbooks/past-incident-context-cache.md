# Past incident: checkout context retained indefinitely

A previous local test showed periodic checkout failures after a context-cache release. A review found new request payloads appended to a module-level list with no eviction. The supervisor restarted the worker at its memory cap, temporarily masking the issue. Rolling back removed the allocations. Treat this as a hypothesis and confirm using current RSS events and the commit diff.
