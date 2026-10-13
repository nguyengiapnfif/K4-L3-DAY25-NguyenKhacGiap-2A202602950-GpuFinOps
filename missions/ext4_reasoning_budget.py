"""Extension 4 — Reasoning budget: what share of traffic, $, tokens and Wh is reasoning?

$ uses M2's optimized pricing (cascade + cache + batch). Wh uses
sustainability.wh_per_query(total_tokens, is_reasoning) per request.

Cap scenario ("only X% of traffic may use reasoning"): if reasoning share s > X, a
fraction f = 1 - X/s of reasoning requests is served in normal mode instead. Each
moved request keeps its input but gets the MEAN output length of non-reasoning
requests on the same route tier (ASSUMPTION: same answer quality is acceptable).
Expected value, so no random sampling. If s <= X nothing changes (savings 0).

Run: python missions/ext4_reasoning_budget.py
"""
from __future__ import annotations
import os as _os, sys as _sys
from collections import defaultdict
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, ROOT
from missions.m2_inference_levers import MODEL_PRICES
from finops import pricing, sustainability

CAPS = (0.10, 0.05, 0.02)   # 10% is the lab's cap; 5% / 2% show what a stricter budget would give


def _cost(r, out_tok=None) -> float:
    pin, pout = MODEL_PRICES[r["route_tier"]]
    return pricing.request_cost(int(num(r["input_tokens"])), out_tok if out_tok is not None else int(num(r["output_tokens"])),
                                pin, pout, cached_in=int(num(r["cached_input_tokens"])), batch=bool(int(num(r["is_batch"]))))


def _wh(r, out_tok=None, reasoning=None) -> float:
    out = out_tok if out_tok is not None else int(num(r["output_tokens"]))
    rs = bool(int(num(r["is_reasoning"]))) if reasoning is None else reasoning
    return sustainability.wh_per_query(int(num(r["input_tokens"])) + out, is_reasoning=rs)


def run(verbose: bool = True, write: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    n = len(rows)
    g = {k: {"n": 0, "tok": 0, "usd": 0.0, "wh": 0.0} for k in (0, 1)}
    outs = defaultdict(list)
    for r in rows:
        k = int(num(r["is_reasoning"]))
        t = int(num(r["input_tokens"])) + int(num(r["output_tokens"]))
        g[k]["n"] += 1; g[k]["tok"] += t; g[k]["usd"] += _cost(r); g[k]["wh"] += _wh(r)
        if not k:
            outs[r["route_tier"]].append(int(num(r["output_tokens"])))
    mean_out = {t: sum(v) / len(v) for t, v in outs.items()}
    T = {f: g[0][f] + g[1][f] for f in ("n", "tok", "usd", "wh")}
    share = g[1]["n"] / n

    pct = lambda f: g[1][f] / T[f] * 100
    mix = ["| metric | normal | reasoning | reasoning share |", "|---|---:|---:|---:|",
           f"| requests | {g[0]['n']:,} | {g[1]['n']:,} | {pct('n'):.1f}% |",
           f"| tokens | {g[0]['tok']:,} | {g[1]['tok']:,} | {pct('tok'):.1f}% |",
           f"| cost $/day | ${g[0]['usd']:,.2f} | ${g[1]['usd']:,.2f} | {pct('usd'):.1f}% |",
           f"| energy Wh/day | {g[0]['wh']:,.0f} | {g[1]['wh']:,.0f} | {pct('wh'):.1f}% |",
           f"| avg Wh / request | {g[0]['wh'] / g[0]['n']:.2f} | {g[1]['wh'] / g[1]['n']:.2f} | x{(g[1]['wh'] / g[1]['n']) / (g[0]['wh'] / g[0]['n']):.0f} |"]

    # per-project: where does reasoning live? (basis for a routing rule)
    proj = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for r in rows:
        p, k = r["project"] or "(untagged)", int(num(r["is_reasoning"]))
        proj[p][0] += 1; proj[p][1] += k
        if k:
            proj[p][2] += _cost(r); proj[p][3] += _wh(r)
    pl = ["| project | requests | reasoning % | reasoning $/day | reasoning Wh/day |", "|---|---:|---:|---:|---:|"]
    for p, (c, k, usd, wh) in sorted(proj.items(), key=lambda kv: -kv[1][3]):
        pl.append(f"| {p} | {c:,} | {k / c * 100:.1f}% | ${usd:,.2f} | {wh:,.0f} |")

    cl = ["| cap | moved to normal | $/day | Wh/day | $ saved/day | $ saved/month | Wh saved/day |", "|---|---:|---:|---:|---:|---:|---:|"]
    caps = []
    for cap in CAPS:
        f = max(0.0, 1.0 - cap / share) if share else 0.0
        usd, wh = g[0]["usd"], g[0]["wh"]
        for r in rows:
            if not int(num(r["is_reasoning"])):
                continue
            mo = mean_out[r["route_tier"]]
            usd += (1 - f) * _cost(r) + f * _cost(r, int(mo))
            wh += (1 - f) * _wh(r) + f * _wh(r, int(mo), reasoning=False)
        sd, sw = T["usd"] - usd, T["wh"] - wh
        caps.append({"cap": cap, "moved_frac": round(f, 4), "usd_saved_day": round(sd, 2), "wh_saved_day": round(sw, 1)})
        cl.append(f"| {cap:.0%} | {f:.0%} | ${usd:,.2f} | {wh:,.0f} | ${sd:,.2f} | ${sd * 30:,.2f} | {sw:,.0f} |")

    top = max(proj.items(), key=lambda kv: kv[1][3])
    top_share = top[1][3] / g[1]["wh"] * 100 if g[1]["wh"] else 0.0
    rule = (f"Routing rule (proposal): reasoning is allowed only for the allow-listed project(s) where it is already used "
            f"('{top[0]}' = {top_share:.0f}% of reasoning energy) and only for multi-step/verifiable tasks; every other project "
            f"(incl. untagged) defaults to normal mode and may escalate to reasoning once when a normal-mode answer scores below a "
            f"confidence threshold. Keep reasoning on the batch path (here 100% batch) so it never competes with interactive "
            f"latency, and track reasoning share / $ / Wh weekly against the 10% budget.")
    why = ("Why ~80x energy: a reasoning model generates long hidden chain-of-thought before answering; decode is memory-bound and "
           "each generated token re-reads the weights and growing KV cache, so energy scales with generated tokens (here reasoning "
           "requests emit ~6x more output tokens) and the lab's 80x multiplier is applied on top of the total-token energy.")
    out = (f"Reasoning is {share:.1%} of requests, {pct('usd'):.1f}% of cost, {pct('wh'):.1f}% of energy.\n\n" + "\n".join(mix) +
           "\n\n## Where reasoning is used\n\n" + "\n".join(pl) + "\n\n## Cap scenarios\n\n" + "\n".join(cl) +
           f"\n\nThe lab's 10% cap is {'already met (traffic is below 10%), so savings = 0' if share <= 0.10 else 'binding'}.\n\n" + rule + "\n\n" + why + "\n")
    if verbose:
        print("== Extension 4: reasoning budget =="); print(out)
    if write:
        with open(_os.path.join(ROOT, "outputs", "ext4_reasoning_budget.md"), "w") as f:
            f.write("# Extension 4 — Reasoning budget\n\n" + out)
    return {"share": share, "usd_share": g[1]["usd"] / T["usd"], "wh_share": g[1]["wh"] / T["wh"], "caps": caps,
            "total_usd": T["usd"], "total_wh": T["wh"]}


if __name__ == "__main__":
    run()
