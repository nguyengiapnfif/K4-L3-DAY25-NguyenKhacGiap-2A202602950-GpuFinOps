# Extension 1 — recommend_tier(): before/after

| job | gpu | spot int. | horizon (mo) | legacy tier | v2 tier | on-demand | legacy (reported) | legacy (re-costed) | v2 |
|---|---|---|---|---|---|---:|---:|---:|---:|
| job-train-llm | H100 | 3% | 0.5 | spot | spot | $12,000 | $7,596 | $7,524 | $7,524 |
| job-train-embed | A100 | 5% | 0.2 | spot | spot | $2,148 | $1,393 | $1,393 | $1,393 |
| job-finetune | H100 | 3% | 0.1 | spot | spot | $900 | $570 | $564 | $564 |
| job-infer-chat | A10G | 8% | 24.0 | reserved | reserved_1yr | $4,320 | $2,592 | $3,888 | $3,456 |
| job-infer-rag | A100 | 5% | 24.0 | reserved | reserved_1yr | $3,866 | $2,160 | $3,240 | $3,024 |
| job-infer-search | L4 | 8% | 24.0 | reserved | reserved_1yr | $1,728 | $972 | $1,458 | $1,296 |
| job-dev-sandbox | A10G | 8% | 0.7 | spot | spot | $480 | $203 | $205 | $205 |
| job-batch-eval | H100 | 3% | 24.0 | spot | spot | $225 | $142 | $141 | $141 |
| **total** | | | | | | **$25,667** | **$15,627** (39.1%) | **$18,413** (28.3%) | **$17,603** (31.4%) |
