# Offline failure analysis

Historical model outputs, audited without API calls. Original v6 results remain unchanged.

| Historical case | Named culprit | New guard | Reason |
|---|---|---|---|
| v6-bad_deploy-agent-openai-gpt-oss-120b-0 | v1.1.0 deployment of checkout-api | pass | Inspected code and cited line match |
| v6-bad_deploy-agent-openai-gpt-oss-20b-0 | v1.1.1 | reject | Named culprit has no service Python code changes; inspect an earlier release rather than blaming metadata |
| v6-bad_deploy-agent-openai-gpt-oss-20b-1 | v1.1.1 | reject | Inspect git_show for the exact release or full SHA named as culprit before submitting |
| v6-bad_deploy-agent-openai-gpt-oss-20b-2 | v1.1.0 | reject | Cite an added or removed service-code line from the inspected revision named as culprit |
| v6-bad_deploy-baseline-openai-gpt-oss-120b-0 | v1.1.0 | reject | Inspect git_show for the exact release or full SHA named as culprit before submitting |

## What failed

The two development-model decoy reports inspected the real code but named the later metadata-only deploy.
Their excerpts were real. The old checks verified provenance but did not connect the named culprit to the inspected diff.

The new guard requires one exact inspected tag/full SHA, a service Python change, and a changed-line citation from that same revision.
It also rejects some historically correct diagnoses that lack the new proof. A rejection is not a claim that the old diagnosis was wrong.

## Fairness and limitations

The v7 baseline now inspects every returned recent deployed diff once using a fixed collection strategy.
Both agent and baseline face the same stricter acceptance rule. v6 CSVs remain frozen and are not rescored as v7.
This is an offline policy audit, not a new LLM benchmark. It proves neither better model accuracy nor that a selected code line logically explains the symptom.
Fresh model evaluation, including independent scenario variants, remains pending free quota.
