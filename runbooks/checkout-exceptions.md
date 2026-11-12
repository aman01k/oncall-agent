# Checkout exceptions after a release

Symptoms: checkout HTTP 500, KeyError or a missing request field. Compare the first error timestamp with recent deploys. Inspect the pricing diff and its parent. A later documentation-only release is not a causal fix. Propose rollback to a known healthy release; verify checkout and history requests recover.
