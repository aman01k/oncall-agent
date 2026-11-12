# Evaluation method

The task is to diagnose three controlled failures from real captured evidence.
Each capture uses the same generic HTTP-error alert. The model never receives
the scenario folder name or answer key. Evidence contains real logs, traffic
metrics, process memory samples, deploys, health results and git diffs.

Each fault has a causal code release and a later metadata-only decoy. Merely
blaming the latest deployment is incorrect. The answer key, stored separately
under `eval/keys/`, accepts the causal tag or its full commit SHA.

The agent chooses follow-up tool calls. The baseline deterministically collects
logs, metrics, deployments, health, a runbook search and every returned recent deployed diff (one per unique SHA),
then asks the same model for one report. Both use the same report schema and
available evidence, with a target budget of 24,000 reported tokens. The baseline has one
model call and no adaptive follow-up. This comparison tests this particular
fixed collection strategy; it does not establish that agents outperform all
possible pipelines.

A run passes only if the failure type and causal release match the key, the
decoy is not named as the culprit, and every cited quote occurs verbatim in its
recorded tool output. The model selects T/E evidence IDs; the application copies
the referenced source text instead of asking the model to reconstruct quotes. Report validation separately requires evidence from two
different tools for a known diagnosis. Confidence is qualitative: high requires
two source types, an observed log/metric citation and an added or removed code-line citation; otherwise it is reduced to medium.

The CSV records every run, including provider failures, invalid reports and
wrong diagnoses. Independent replicates use distinct seeds. Identical requests
can be resumed from the response cache; `cached_calls` reports this explicitly.
Reusing a finished run is a resume operation, not another independent trial.

Generate fresh real snapshots and run both methods:

```bash
python scripts/build_fixtures.py
python scripts/leak_check.py
python -m eval.evaluate --model openai/gpt-oss-120b --runs 1
python scripts/record_replays.py
```

Increase `--runs` to 5 for a larger set of independent seeds when the free
quota permits. Results land in `eval/results/`. Do not call three scenarios a
large benchmark: one capture per fault and a few runs cannot support statistical
significance, production accuracy or claims about real-world recovery time.

Snapshot clocks are fixed, tools are read-only and each output is capped at
4,000 characters. The leak audit checks unexpected evidence files, obvious
credentials and answer metadata. It cannot prove that synthetic scenarios have
no other shortcuts. All fixture traffic is synthetic.

The token target is a soft limit: the loop forces finalization near 21,000
reported tokens, and the final response can take it above 24,000. The 12-step
limit is hard. Reported token totals cover successful responses; a provider may
consume quota on a rejected request without returning usage. Pilot runs during
development used different report-format settings and are retained separately
from the final experiment version.

The final report protocol selects T/E source references and copies quotes in
application code. This prevents invented excerpts, but citation relevance still
needs a stronger semantic evaluation. `provider_tokens` counts known successful
noncached response usage; `total_tokens` also includes cached responses. Earlier
records may not have the provider_tokens field. Rejected requests can consume
quota without exposing usage.

The provider reported a 200,000-token daily cap for the main model during
integration. Use `--retry-failed` after replenishment to archive failed attempts
and resume them from cache. Completed wrong diagnoses are preserved as outcomes.
See [pilot results](evaluation-results.md) for the actual counts and limitations.

## Protocol v7

Known diagnoses now require an exact inspected tag/full SHA, changed service Python code, and a citation to an added or removed line from that same revision. The rule applies to agent and baseline. The fixed collector now inspects every returned recent deployed diff once rather than adapting to the model's hypotheses. This avoids making the old baseline unable to satisfy the new rule.

This check establishes structural provenance only. It does not prove that the line causes the symptom or cover all real-world causes such as infrastructure/configuration changes or rename-only changes. It can increase inconclusive reports. Measure that trade-off with fresh model runs, not the offline tests.

The v6 tables remain unchanged. New runs default to v7. Historical experiment names cannot resume under the new policy. Offline regression bundles contain actual historical model outputs with machine paths and provider organization IDs redacted. They are never counted as new model trials.
