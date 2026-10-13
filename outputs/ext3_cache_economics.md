# Extension 3 — cache_is_worth_it(): before/after

```
M2 optimized (cache write ignored): $8.48/day = $1.126/1M-token
Same routing/batch, caching disabled: $9.66/day = $1.282/1M-token
Break-even reads per prefix (write 1.25x, read 0.1x): 0.278  ->  reads=0.25 loses, reads=1 wins
```

| avg reads / prefix | cache used? | requests cached | optimized $/day | $/1M-token | vs M2 (no write cost) |
|---:|---|---:|---:|---:|---:|
| 0.1 | no | 0/2400 | $9.66 | $1.282 | +13.8% |
| 0.25 | no | 0/2400 | $9.66 | $1.282 | +13.8% |
| 0.5 | yes | 2400/2400 | $9.14 | $1.213 | +7.7% |
| 1 | yes | 2400/2400 | $8.81 | $1.170 | +3.8% |
| 3 | yes | 2400/2400 | $8.59 | $1.141 | +1.3% |
| 10 | yes | 2400/2400 | $8.52 | $1.131 | +0.4% |
