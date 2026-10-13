"""Extension 3 — cache_is_worth_it(): put the cache WRITE cost back into M2.

M2 bills cached input at 10% of price but never charges for creating the cache,
so its savings are an upper bound. Here every request that has cached tokens
pays an extra write premium amortised over `reads` re-reads of the prefix, and the
cache is only used when pricing.cache_is_worth_it() says reads > break-even.

ASSUMPTIONS (the CSV has no reads-per-prefix or write price):
  - write premium = (WRITE_MULT - 1) x input price  (Anthropic 5-min write = 1.25x)
  - `reads` = average re-reads per cached prefix, swept below.

Run: python missions/ext3_cache_economics.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, ROOT
from missions.m2_inference_levers import MODEL_PRICES
from finops import pricing

WRITE_MULT = 1.25
READS_SWEEP = (0.1, 0.25, 0.5, 1, 3, 10)


def optimized_cost(rows, reads: float, write_mult: float = WRITE_MULT):
    cost = tokens = 0.0
    used = 0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        pin, pout = MODEL_PRICES[r["route_tier"]]
        batch = bool(int(num(r["is_batch"])))
        tokens += inp + out
        write_extra = (write_mult - 1.0) * pin
        if cached and pricing.cache_is_worth_it(reads, write_extra, price_in_per_m=pin):
            c = pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=batch)
            # write premium for the cached prefix, spread over `reads` uses; batch discount applies
            c += (cached / 1e6) * write_extra / reads * (0.5 if batch else 1.0)
            used += 1
        else:
            c = pricing.request_cost(inp, out, pin, pout, cached_in=0, batch=batch)
        cost += c
    return cost, tokens, used


def run(verbose: bool = True, write: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    n_cached = sum(1 for r in rows if int(num(r["cached_input_tokens"])))
    legacy, tokens, _ = optimized_cost(rows, reads=1e12, write_mult=1.0)  # = M2 optimized (no write cost)
    no_cache = optimized_cost([dict(r, cached_input_tokens="0") for r in rows], reads=1)[0]
    be = pricing.cache_break_even_reads((WRITE_MULT - 1.0) * 1.0, price_in_per_m=1.0)

    lines = ["| avg reads / prefix | cache used? | requests cached | optimized $/day | $/1M-token | vs M2 (no write cost) |",
             "|---:|---|---:|---:|---:|---:|"]
    sweep = []
    for k in READS_SWEEP:
        c, _, used = optimized_cost(rows, reads=k)
        pm = pricing.dollars_per_million(c, tokens)
        sweep.append({"reads": k, "cost": round(c, 2), "per_m": round(pm, 3), "cached_requests": used})
        lines.append(f"| {k} | {'yes' if used else 'no'} | {used}/{n_cached} | ${c:,.2f} | ${pm:.3f} | {(c / legacy - 1) * 100:+.1f}% |")
    table = "\n".join(lines)
    head = (f"M2 optimized (cache write ignored): ${legacy:,.2f}/day = ${pricing.dollars_per_million(legacy, tokens):.3f}/1M-token\n"
            f"Same routing/batch, caching disabled: ${no_cache:,.2f}/day = ${pricing.dollars_per_million(no_cache, tokens):.3f}/1M-token\n"
            f"Break-even reads per prefix (write {WRITE_MULT}x, read 0.1x): {be:.3f}  ->  reads=0.25 loses, reads=1 wins")
    if verbose:
        print("== Extension 3: cache_is_worth_it ==")
        print(head); print(); print(table)
    if write:
        with open(_os.path.join(ROOT, "outputs", "ext3_cache_economics.md"), "w") as f:
            f.write("# Extension 3 — cache_is_worth_it(): before/after\n\n```\n" + head + "\n```\n\n" + table + "\n")
    return {"break_even_reads": round(be, 4), "m2_optimized_daily": round(legacy, 2),
            "no_cache_daily": round(no_cache, 2), "sweep": sweep}


if __name__ == "__main__":
    run()
