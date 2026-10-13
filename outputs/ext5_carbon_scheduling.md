# Extension 5 — Carbon-aware scheduling

## Per job

| job | gpu | GPU-h | kWh | gCO2e @us-east-1 | gCO2e @europe-north1 | saved g | saved % |
|---|---|---:|---:|---:|---:|---:|---:|
| job-train-llm | H100 | 2,240 | 1,568.0 | 595,840 | 47,040 | 548,800 | 92% |
| job-train-embed | A100 | 200 | 80.0 | 30,400 | 2,400 | 28,000 | 92% |
| job-finetune | H100 | 36 | 25.2 | 9,576 | 756 | 8,820 | 92% |
| job-dev-sandbox | A10G | 352 | 52.8 | 20,064 | 1,584 | 18,480 | 92% |
| job-batch-eval | H100 | 90 | 63.0 | 23,940 | 1,890 | 22,050 | 92% |
| **total** | | 2,918 | **1,789.0** | **679,820** | **53,670** | **626,150** | **92%** |

## All five regions (same work, same GPU-hours)

| region | $/kWh | gCO2/kWh | electricity $ | gCO2e | vs us-east-1 CO2 | latency (assumed) | pick |
|---|---:|---:|---:|---:|---:|---|---|
| us-east-1 | 0.12 | 380 | $214.68 | 679,820 | +0% | baseline |  |
| us-west-2 | 0.07 | 120 | $125.23 | 214,680 | -68% | +60-70 ms RTT |  |
| europe-north1 | 0.09 | 30 | $161.01 | 53,670 | -92% | +100-120 ms RTT | cleanest |
| europe-central2 | 0.18 | 660 | $322.02 | 1,180,740 | +74% | +90-110 ms RTT |  |
| us-east-wa | 0.055 | 90 | $98.39 | 161,010 | -76% | +60-70 ms RTT | cheapest $, balanced |

cheapest $: us-east-wa | cleanest: europe-north1 | balanced (50/50 min-max of $ and CO2): us-east-wa
Moving all interruptible jobs us-east-1 -> europe-north1: 626.1 kgCO2e saved (92%), electricity $214.68 -> $161.01.
