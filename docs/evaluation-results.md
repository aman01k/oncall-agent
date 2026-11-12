# Pilot evaluation results

Experiment: **v6**. Real captured evidence; no simulated LLM responses.

| Model | Method | Attempts | Completed reports | Correct | Wrong completed | Quota-limited |
|---|---|---:|---:|---:|---:|---:|
| openai/gpt-oss-120b | agent | 3 | 1 | 1 | 0 | 2 |
| openai/gpt-oss-120b | baseline | 3 | 1 | 1 | 0 | 2 |
| openai/gpt-oss-20b | agent | 5 | 3 | 1 | 2 | 2 |
| openai/gpt-oss-20b | baseline | 5 | 0 | 0 | 0 | 5 |

The main-model batch covers all three faults once. The development-model batch covers five bad-deploy seeds.
These are different task sets; do not compare their totals as equivalent benchmarks.

Quota-limited attempts are retained in the CSV as failures to complete, but are not called wrong diagnoses.
A completed report can still be incorrect (wrong type, wrong culprit or decoy blamed).

In the main-model bad-deploy trial, both methods correctly identified the cause. That trial does not show an accuracy advantage for the agent.
The incomplete batches cannot support a general accuracy or superiority claim.

Earlier development experiments remain in separate CSVs. They used evolving report protocols and are not pooled into v6.

## Resume after free quota replenishes

```bash
python -m eval.evaluate --model openai/gpt-oss-120b --runs 1 --experiment v6 --retry-failed
python -m eval.evaluate --model openai/gpt-oss-20b --scenario bad_deploy --runs 5 --experiment v6 --retry-failed
```

Failed attempts are archived before retry; completed diagnoses, including wrong ones, are never rerun by this option.
A cached prefix can resume without repeating every API request. A resumed attempt is not another independent trial.
