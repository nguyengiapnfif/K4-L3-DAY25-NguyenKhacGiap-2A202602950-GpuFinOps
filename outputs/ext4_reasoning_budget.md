# Extension 4 — Reasoning budget

Reasoning is 8.4% of requests, 16.5% of cost, 94.0% of energy.

| metric | normal | reasoning | reasoning share |
|---|---:|---:|---:|
| requests | 2,199 | 201 | 8.4% |
| tokens | 6,291,871 | 1,241,156 | 16.5% |
| cost $/day | $7.09 | $1.40 | 16.5% |
| energy Wh/day | 1,888 | 29,788 | 94.0% |
| avg Wh / request | 0.86 | 148.20 | x173 |

## Where reasoning is used

| project | requests | reasoning % | reasoning $/day | reasoning Wh/day |
|---|---:|---:|---:|---:|
| nightly-eval | 381 | 47.5% | $1.24 | 26,902 |
| (untagged) | 197 | 10.2% | $0.15 | 2,885 |
| doc-qa | 517 | 0.0% | $0.00 | 0 |
| web-search | 573 | 0.0% | $0.00 | 0 |
| chat | 732 | 0.0% | $0.00 | 0 |

## Cap scenarios

| cap | moved to normal | $/day | Wh/day | $ saved/day | $ saved/month | Wh saved/day |
|---|---:|---:|---:|---:|---:|---:|
| 10% | 0% | $8.48 | 31,675 | $0.00 | $0.00 | 0 |
| 5% | 40% | $8.07 | 19,743 | $0.41 | $12.41 | 11,933 |
| 2% | 76% | $7.70 | 9,136 | $0.78 | $23.44 | 22,539 |

The lab's 10% cap is already met (traffic is below 10%), so savings = 0.

Routing rule (proposal): reasoning is allowed only for the allow-listed project(s) where it is already used ('nightly-eval' = 90% of reasoning energy) and only for multi-step/verifiable tasks; every other project (incl. untagged) defaults to normal mode and may escalate to reasoning once when a normal-mode answer scores below a confidence threshold. Keep reasoning on the batch path (here 100% batch) so it never competes with interactive latency, and track reasoning share / $ / Wh weekly against the 10% budget.

Why ~80x energy: a reasoning model generates long hidden chain-of-thought before answering; decode is memory-bound and each generated token re-reads the weights and growing KV cache, so energy scales with generated tokens (here reasoning requests emit ~6x more output tokens) and the lab's 80x multiplier is applied on top of the total-token energy.
